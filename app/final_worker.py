import argparse
import os
from app.database.session import create_database
from app.services.final_render_service import run_final


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True);parser.add_argument('--database-url',required=True)
    args=parser.parse_args();sessions=create_database(args.database_url)
    run_final(sessions,args.job);sessions.kw['bind'].dispose();os._exit(0)
