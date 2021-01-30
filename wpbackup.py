import argparse
import logging
import os
import subprocess
from subprocess import PIPE
import tempfile
import tarfile
import shutil

#from wpconfigr import WpConfigFile
from wpconfigr.wp_config_file import WpConfigFile

DB_DUMP_ARCNAME = 'database.sql'
WP_DIR_ARCNAME = 'wp-root'

'''
TODO:
    - create cleanup module on failure.
'''

def run_cli():
    arg_parser = argparse.ArgumentParser(
        description='Backup and restore all your self-hosted WordPress '
            'content.',
        prog='python -m wordpressbackup')

    arg_parser.add_argument('--backup',
        action='store_true',
        help='Perform a backup')

    arg_parser.add_argument('--restore',
        action='store_true',
        help='Perform a restoration')

    arg_parser.add_argument('--wp-dir',
        help='Path to the root of the WordPress directory',
        required=True)

    arg_parser.add_argument('--archive',
        help='Path and filename of the archive (.tar.gz) '
            'to backup to/restore from.',
        required=True)

    arg_parser.add_argument('--db-host',
        help='Database hostname. Required only for '
            'restorations.',
        default="",
        required=False)
        
    arg_parser.add_argument('--db-port',
        help='Database port. Required only for '
            'restorations.',
        default=3306,
        required=False)
    
    arg_parser.add_argument('--db-username',
        help='Database admin username. Required only for '
            'restorations.',
        default="",
        required=False)

    arg_parser.add_argument('--db-password',
        help='Database admin password. Required only for '
            'restorations.',
        default="",
        required=False)
        
    arg_parser.add_argument('--db-name',
        help='Database name where worppress will be backed up to.'
            ' Required only for restorations.',
        default="",
        required=False)
        
    arg_parser.add_argument('--log-level',
        default='CRITICAL',
        help='Log level',
        required=False)
        
    args = arg_parser.parse_args()
        
        
    if args.backup == args.restore:
        arg_parser.error('Must specify either --backup or --restore.')
    
    logging.basicConfig(level=str(args.log_level).upper())
    log = logging.getLogger(__name__)
    
    if os.geteuid() != 0:
        log.fatal('This script is not being run as root.')
        exit(5)
    
    if args.backup:
        backup(wp_dir=args.wp_dir,
                arc_filename=args.archive,
                log=log)
    elif args.restore:
        if args.db_username == "" or args.db_password == "":
            arg_parser.error('--db-username and --db-password must be included'
                            ' when using --restore.')
        else:
            
            restore(wp_dir=args.wp_dir,
                    arc_filename=args.archive,
                    db_user=args.db_username,
                    db_pass=args.db_password,
                    db_host=args.db_host,
                    db_port=args.db_port,
                    db_name=args.db_name,
                    log=log
            )
        

    
def dump_database(wp_config_filename, db_dump_filename, log):
    wp_config = WpConfigFile(wp_config_filename)
    
    tmp_login_file = ['[mysqldump]','user='+wp_config.get('DB_USER'),'password='+wp_config.get('DB_PASSWORD')]
    
    with open('/root/.my.cnf', 'w') as stream:
        for line in tmp_login_file:
            stream.write(line+'\n')
    
    if ':' in wp_config.get('DB_HOST'):
        hostinfo = wp_config.get('DB_HOST').split(':')
        db_host = hostinfo[0]
        db_port = hostinfo[1]
    else:
        db_host = wp_config.get('DB_HOST')
        db_port = 3306
        
    args = [
        'mysqldump',
        '-h',
        db_host,
        '-P',
        str(db_port),
        '-u',
        wp_config.get('DB_USER'),
        wp_config.get('DB_NAME')
    ]
    
    log.info('Getting database dump...')
    log.info(args)
    
    try:
        #completed = subprocess.run(args, capture_output=True) # <- introduced in python 3.7
        completed = subprocess.run(args, stdout=PIPE, stderr=PIPE)
    except FileNotFoundError as error:
        log.fatal(error)
        log.fatal('mysqldump was not found. Please install it and try again.')
        exit(1)
        
    if completed.returncode != 0:
        log.fatal('Database backup failed.\n\nmysqldump stdout:\n%s\n\nmysql '
                  'stderr:\n%s',
                  completed.stdout,
                  completed.stderr)
        exit(2)
        
    log.info('Saving database dump to "%s"...', db_dump_filename)
    
    with open(db_dump_filename, 'wb') as stream:
        stream.write(completed.stdout)
        
    os.remove('/root/.my.cnf')
        
    log.info('Database dump complete.')
    
def restore_database(wp_config_filename, db_dump_filename, db_user, db_pass, db_host, db_port, db_name, log):
    wp_config = WpConfigFile(wp_config_filename)
    
    if db_host == "":
        hostinfo = wp_config.get('DB_HOST')
        if ':' in hostinfo:
            hostinfo = hostinfo.split(':')
            db_host = hostinfo[0]
            db_port = hostinfo[1]
        else:
            db_host = hostinfo
            db_port = 3306
            
    else:
        if db_port == 3306:
            wp_config.set('DB_HOST', db_host)
        else:
            hostinfo = f"{db_host}:{str(db_port)}"
            wp_config.set('DB_HOST', hostinfo)
    
    if db_name == "":
        db_name = wp_config.get('DB_NAME')
    else:
        wp_config.set('DB_NAME', db_name)
        
    wp_config.set('DB_USER', db_user)
    wp_config.set('DB_PASSWORD', db_pass)
    
    tmp_login_file = ['[mysql]','user='+db_user,'password='+db_pass]
        
    with open('/root/.my.cnf', 'w') as stream:
        for line in tmp_login_file:
            stream.write(line+'\n')
    
    restore_args = [
        'mysql',
        '-h',
        db_host,
        '-P',
        db_port,
        '-u',
        db_user,
        db_name,
        '--execute',
        'source {};'.format(db_dump_filename)
    ]
    
    try: 
        log.info('Copying database backup in to MySQL...')
        #completed = subprocess.run(restore_args, capture_output=True) # <- introduced in python 3.7
        completed = subprocess.run(restore_args, stdout=PIPE, stderr=PIPE)
    except FileNotFoundError as error:
        log.fatal(error)
        log.fatal('mysql command was not found. Please install it and try again.')
        exit(1)
    
    if completed.returncode != 0:
        LOG.fatal('Database restoration failed.\n\nmysql stdout:\n%s\n\n'
                  'mysql stderr:\n%s',
                  completed.stdout,
                  completed.stderr)
        exit(2)
    
    os.remove('/root/.my.cnf')
    
    log.info('Database restoration complete.')
    
def backup(wp_dir, arc_filename, log):
    log.info('Starting backup...')
    
    temp_dir = tempfile.TemporaryDirectory()
    
    log.info('Building archive content in: %s', temp_dir.name)
    
    db_dump_path = os.path.join(temp_dir.name, DB_DUMP_ARCNAME)
    wp_config_filename = os.path.join(wp_dir, 'wp-config.php')
    
    if not os.path.exists(wp_config_filename):
        log.fatal('wp-config.php could not be found at: %s', wp_config_filename)
        exit(3)
        
    dump_database(wp_config_filename=wp_config_filename,
                    db_dump_filename=db_dump_path,
                    log=log)
                    
    log.info('Creating archive: %s', arc_filename)
    with tarfile.open(arc_filename, 'w:gz') as stream:
        log.info('Adding database dump "%s" to archive "%s"...', db_dump_path, arc_filename)
        stream.add(db_dump_path, arcname=DB_DUMP_ARCNAME)
        
        log.info('Adding wordpress directory "%s" to archive "%s"...', wp_dir, arc_filename)
        stream.add(wp_dir, arcname=WP_DIR_ARCNAME)
        
    log.info('Backup Complete')
    
def restore(wp_dir, arc_filename, db_user, db_pass, db_host, db_port, db_name, log):
    log.info('Starting restoration')
    
    temp_dir = tempfile.TemporaryDirectory()
    
    log.info('Will unzip the archive in: %s', temp_dir.name)
    
    db_dump_path = os.path.join(temp_dir.name, DB_DUMP_ARCNAME)
    log.info('will extract the database dump to: %s', db_dump_path)
    
    tmp_wp_dir_path = os.path.join(temp_dir.name, WP_DIR_ARCNAME)
    log.info('Will extract wordpress to: %s', tmp_wp_dir_path)
    
    if os.path.exists(wp_dir):
        log.info('Wordpress is already installed on this server. exiting...')
        exit(1)
        # create wp_dir 
        
    log.info('Opening archive: %s', arc_filename)
    with tarfile.open(arc_filename, 'r:gz') as stream:
        log.info('Extracting wordpress directory "%s" to "%s"...',
                WP_DIR_ARCNAME,
                ap_dir)
                
        root_dir = WP_DIR_ARCNAME + os.path.sep
        root_dir_len = len(root_dir)
        
        wp_members = []
        
        for member in stream.getmembers():
            if member.path.startswith(root_dir):
                member.path = member.path[root_dir_len:]
                wp_members.append(member)
                
        stream.extractall(members=wp_members, path=wp_dir)
        
        log.info('Extracting database dump "%s" to "%s"...',
                DB_DUMP_ARCNAME,
                temp_dir.name)
        stream.extract(DB_DUMP_ARCNAME, path=temp_dir.name)
        
        wp_config_filename = os.path.join(wp_dir, 'wp-config.php')
        
        restore_database(
            wp_config_filename=wp_config_filename,
            db_dump_filename=db_dump_path,
            db_user=db_user,
            db_pass=db_pass,
            db_host=db_host,
            db_port=db_port,
            db_name=db_name,
            log=log    
        )
        
    log.info('Restoration complete.')
            
if __name__ == '__main__':
    run_cli()
    