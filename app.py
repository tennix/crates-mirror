import os
import json
import asyncio
import sqlite3
import threading
import logging
import hashlib
from datetime import datetime

import requests
from git import Repo

dl = "https://crates.io/api/v1/crates/{name}/{version}/download"

proxies = {
    "http": "http://localhost:8123",
    "https": "http://localhost:8123"
}

max_connection = 10
chunk_size = 512 * 1024

index_url = "https://github.com/rust-lang/crates.io-index"
work_dir = os.getcwd()
registry_path = os.path.join(work_dir, "crates.io-index")
crates_path = os.path.join(work_dir, "crates")
ignore = os.path.join(registry_path, ".git")
db_path = os.path.join(work_dir, "crates.db")

logging.basicConfig(filename="mirror.log",
                    format="%(asctime)s: %(message)s",
                    level=logging.INFO)

def initialize_db():
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
    else:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""create table crate (
                         id integer primary key,
                         name text,
                         version text,
                         size integer default 0,
                         checksum text,
                         yanked integer default 0,
                         downloaded integer default 0,
                         last_update text
                     )""")
        c.execute("""create table update_history (
                         commit_id text,
                         timestamp text
                     )""")
        conn.commit()
    return conn


def initialize_repo():
    if os.path.exists(registry_path):
        repo = Repo(registry_path)
    else:
        repo = Repo.clone_from(index_url, registry_path)
    conn.cursor().execute("insert into update_history values (?, ?)", (str(repo.commit()), datetime.now()))
    conn.commit()
    return repo


def load_info():
    cur = conn.cursor()
    cur.execute("select count(id) from crate")
    if cur.fetchone()[0] != 0:          # info already loaded
        return
    for root, dirs, files in os.walk(registry_path):
        for f in files:
            if not root.startswith(ignore) and f != "config.json":
                index_path = os.path.join(root, f)
                with open(index_path, 'r') as json_file:
                    for line in json_file.readlines():
                        crate = json.loads(line)
                        conn.cursor().execute("insert into crate (name, version, checksum, yanked) values (?, ?, ?, ?)",
                                              (crate["name"], crate["vers"], crate["cksum"], int(crate["yanked"])))
    conn.commit()


async def download_crate(name, version, checksum):
    filename = name + "-" + version + ".crate"
    if len(name) == 1:
        directory = os.path.join(crates_path, '1', name)
    elif len(name) == 2:
        directory = os.path.join(crates_path, '2', name)
    elif len(name) == 3:
        directory = os.path.join(crates_path, '3', name[:1], name)
    else:
        directory = os.path.join(crates_path, name[:2], name[2:4], name)
    if not os.path.exists(directory):
        os.makedirs(directory)
    crate_path = os.path.join(directory, filename)
    r = requests.get(dl.format(name=name, version=version), proxies=proxies, stream=True)
    with open(crate_path, "wb") as fd: # is chunk needed here?
        for chunk in r.iter_content(chunk_size=chunk_size):
            fd.write(chunk)
    with open(crate_path, "rb") as fd:
        content = fd.read()
        if hashlib.sha256(content).hexdigest() == checksum:
            logging.info("%s download success" % filename)
            return True, len(content)
    # download failed
    logging.warning("%s download failed, I will try again later" % filename)
    os.remove(crate_path)
    return False, 0


async def retrieve_crate(name, version, checksum):
    success, size = await download_crate(name, version, checksum)
    sql = "update crate set downloaded = ?, size = ?,  last_update = ? where name = ? and version = ?"
    conn.cursor().execute(sql, (int(success), size, datetime.now(), name, version))
    conn.commit()


def retrieve_crates():
    cur = conn.cursor()
    cur.execute("select name, version, checksum from crate where downloaded = 0")
    crates = cur.fetchmany(max_connection)
    loop = asyncio.get_event_loop()
    while crates:
        tasks = [asyncio.ensure_future(retrieve_crate(name, version, checksum)) for name, version, checksum in crates]
        loop.run_until_complete(asyncio.wait(tasks))
        crates = cur.fetchmany(max_connection)
    

def get_crate_info(name, version):
    if len(name) == 1:
        index_path = os.path.join(registry_path, '1', name)
    elif len(name) == 2:
        index_path = os.path.join(registry_path, '2', name)
    elif len(name) == 3:
        index_path = os.path.join(registry_path, '3', name[:1], name)
    else:
        index_path = os.path.join(registry_path, name[:2], name[2:4], name)
    with open(index_path, 'r') as f:
        for line in f.readline():
            crate = json.load(line)
            if crate["vers"] == version:
                return crate
    return None


def _take(n, iterable):
    import itertools
    return list(itertools.islice(iterable, n))


def update_repo():
    cur.execute("select commit_id from update_history order by datetime(timestamp) desc limit 1")
    last_update = cur.fetchone()
    origin = repo.remotes['origin']
    logging.info("Updating repo")
    origin.pull()
    commits = repo.iter_commits()
    crates = []
    for commit in commits:
        if str(commit) != last_update:
            msg = commit.message
            if msg.startswith('Updating'):
                name, version = msg.split('`')[1].split('#')
                crate = get_crate_info(name, version)
                crates.append(crate)
        else:
            break
    cur.execute("insert into update_history (commit_id, timestamp) values (?, ?)",
                (str(repo.commit()), datetime.now()))
    conn.commit()
    it = iter(crates)
    crates = _take(max_connection, it)
    loop = asyncio.get_event_loop()
    while crates:
        tasks = []
        for crate in crates:
            tasks.append(asyncio.ensure_future(retrieve_crate(crate["name"], crate["vers"], crate["cksum"])))
        loop.run_until_complete(asyncio.wait(tasks))
        crates = _take(max_connection, it)



if __name__ == "__main__":
    conn = initialize_db()
    repo = initialize_repo()
    load_info()
    retrieve_crates()
    t1 = threading.Timer(10*60.0, update_repo) # update repo every 10 minutes
    t2 = threading.Timer(30*60.0, retrieve_crates) # retrieve failed download every 30 minutes
    logging.info("Starting scheduled job")
    t1.start()
    t2.start()
