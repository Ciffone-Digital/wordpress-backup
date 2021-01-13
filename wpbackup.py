import argparse
import logging
import os
import subprocess
import tempfile
import tarfile
import shutil

from wpconfigr import WpConfigFile
from wpdatabase.classes import Credentials

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
    
    if args.backup:
        backup(wp_dir=args.wp_dir,
                arc_filename=args.archive,
                log=log)
    elif args.restore:
        if args.db_username == "" or args.db_password == "":
            arg_parser.error('--db-username and --db-password must be included'
                            ' when using --restore.')
        else:
            credentials = Credentials.from_username_and_password(
                username=args.db_username,
                password=args.db_password
            )
            
            restore(wp_dir=args.wp_dir,
                    arc_filename=args.archive,
                    admin_creds=credentials,
                    db_host=args.db_host,
                    db_name=args.db_name,
                    log=log
            )
        

    
def dump_database(wp_config_filename, db_dump_filename, log):
    wp_config = WpConfigFile(wp_config_filename)
    
    args = [
        'mysqldump',
        '-h',
        wp_config.get('DB_HOST'),
        '-u',
        wp_config.get('DB_USER'),
        '\'--password='+wp_config.get('DB_PASSWORD')+'\'',
        wp_config.get('DB_NAME')
    ]
    
    log.info('Getting database dump...')
    
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
        
    log.info('Database dump complete.')
    
def restore_database(wp_config_filename, db_dump_filename, admin_credentials, db_host, db_name, log):
    wp_config = WpConfigFile(wp_config_filename)
    if db_host == "":
        db_host = wp_config.get('DB_HOST')
    else:
        wp_config.set('DB_HOST', db_host)
    
    if db_name == "":
        db_name = wp_config.get('DB_NAME')
    else:
        wp_config.set('DB_NAME', db_name)
        
    wp_config.set('DB_USER', admin_credentials.username)
    wp_config.set('DB_PASSWORD', admin_credentials.password)
        
    '''
    NOTE: ansible script will create the database, and 
    the user for wordpress to connect to mysql.
    
    create_args = [
        'mysql',
        '--host',
        db_host,
        '--user',
        admin_credentials.username,
        '\'--password='+admin_credentials.password+'\'',
        '--execute',
        'CREATE DATABASE IF NOT EXISTS {};'.format(db_name)
    ]
    '''
    
    restore_args = [
        'mysql',
        '--host',
        db_host,
        '--user',
        admin_credentials.username,
        '\'--password='+admin_credentials.password+'\'',
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
        stream.add(db_dump_path, arcname=DB_BUMP_ARCNAME)
        
        log.info('Adding wordpress directory "%s" to archive "%s"...', wp_dir, arc_filename)
        stream.add(wp_dir, arcname=WP_DIR_ARCNAME)
        
    log.info('Backup Complete')
    
def restore(wp_dir, arc_filename, admin_creds, db_host, db_name, log):
    log.info('Starting restoration')
    
    temp_dir = tempfile.TemporaryDirectory()
    
    log.info('Will unzip the archive in: %s', temp_dir.name)
    
    db_dump_path = os.path.join(temp_dir.name, DB_DUMP_ARCNAME)
    log.info('will extract the database dump to: %s', db_dump_path)
    
    tmp_wp_dir_path = os.path.join(temp_dir.name, WP_DIR_NAME)
    log.info('Will extract wordpress to: %s', tmp_wp_dir_path)
    
    if os.path.exists(wp_dir):
        log.info('Wordpress is already installed on this server. exiting...')
        exit(4)
        
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
            admin_credentials=admin_creds,
            db_host=db_host,
            db_name=db_name,
            log=log    
        )
        
    log.info('Restoration complete.')
            
if __name__ == '__main__':
    run_cli()
    