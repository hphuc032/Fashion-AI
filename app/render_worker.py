import argparse
import os
from app.database.session import create_database
from app.services.render_jobs import run_render

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',required=True)
    parser.add_argument('--database-url',required=True)
    args=parser.parse_args()
    sessions=create_database(args.database_url)
    run_render(sessions,args.job)
    sessions.kw['bind'].dispose()
    os._exit(0)
