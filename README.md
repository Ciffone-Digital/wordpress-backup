# wordpress-backup
Python script for backing and restoring wordpress installations.

## pre-requisites
Run the following command to install the neccessary libraries for this script:
```
pip3 install -r requirements.txt
```

## Running
### backup
you can run the command as follows:
```
python3 wpbackup.py --backup --wp-dir="/path/to/wordpress/install/" --archive="/path/to/archive.tar.gz"
```
### restore
you can run the command as follows:
```
python3 wpbackup.py --restore --wp-dir="/path/to/install/wordpress/" --archive="/path/to/archive.tar.gz" --db-username="wpuser" --db-password="wppass"
```
you can also specify the db host, db port, or db name:
```
python3 wpbackup.py --restore --wp-dir="/path/to/install/wordpress/" --archive="/path/to/archive.tar.gz" --db-username="wpuser" --db-password="wppass" --db-host="localhost" --db-port=3306 --db-name="wordpress"
```
