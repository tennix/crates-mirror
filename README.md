# Crates Mirror

Download all crates on [Rust official crates site](https://crates.io)
and keep sync with it. This can be used to setup a static mirror site
of https://crates.io.  This can be used with
[cargo-mirror](https://github.com/tennix/cargo-mirror) to make
dependency download faster when building Rust project.

## Requirements
* Python3 (yes python3, python2 is dead)
* Good bandwidth (at least can access aws-s3 service of us region)
* Large hard disk (at least 3G, I downloaded all crates to my computer, it's about 2G atm.)

## How
1. Clone this repo: `git clone https://github.com/tennix/crates-mirror`
2. Fire a python virtualenv:
   ```
   cd crates-mirror
   pyvenv env
   source env/bin/activate
   pip install -r requirements.txt
   ```
3. Run this program: `python app.py`
4. (Optional)Serve a mirror site:
   ```
   cd crates
   python -m http.server 8000
   ```

*Note*: for production, you should make this program auto-restarted
 when dies ([supervisord](http://supervisord.org) like tools is
 needed). And also use a production web server (nginx, apache etc.) to
 serve the mirror site
