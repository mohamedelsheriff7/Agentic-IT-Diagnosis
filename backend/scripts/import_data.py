"""Explicit authenticated import/reset CLI; run from project root."""
import argparse
import hmac
import os
from pathlib import Path
from sqlalchemy import text
from app.config import Settings,ROOT
from app.models import database
from app.importer import import_dataset

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,default=ROOT/'data');p.add_argument('--reset',action='store_true');p.add_argument('--confirm');p.add_argument('--validate-only',action='store_true')
    args=p.parse_args();settings=Settings.from_env()
    key=os.getenv('ADMIN_COMMAND_KEY','')
    if not settings.admin_api_key or not key or not hmac.compare_digest(key,settings.admin_api_key): p.error('ADMIN_COMMAND_KEY must match ADMIN_API_KEY')
    if args.reset and args.confirm!='RESET_SYNTHETIC_DEMO': p.error('Reset requires --confirm RESET_SYNTHETIC_DEMO')
    engine,sessions=database('sqlite:///:memory:' if args.validate_only else settings.database_url)
    with sessions() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        try:
            count=import_dataset(db,args.data_dir,args.reset)
            db.commit()
        except Exception:
            db.rollback();raise
    engine.dispose()
    print(f'{"Validated" if args.validate_only else "Imported"} {count} tickets; evaluation files excluded')
if __name__=='__main__': main()
