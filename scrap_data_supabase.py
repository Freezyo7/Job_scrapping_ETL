from airflow.decorators import dag, task
from airflow.hooks.base import BaseHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.utils.dates import days_ago
from sqlalchemy import create_engine, text
from io import StringIO
import pandas as pd
import yaml
import os
from datetime import datetime, timedelta, timezone

@dag(
    dag_id = "output_to_supabase_dag",
    schedule_interval = "30 12 * * *",
    start_date = days_ago(1),
    catchup = False,
    tags = ["Job", "csv", "supabase"]
)

def dag_main():

    @task()
    def read_config_from_s3():
        bucket_name = "webscrap-bucket-store"
        key = "Job_data/Automation/dynamic/output_config.yml"
        aws_conn_id = "webscrap_bucket_s3_conn"

        s3 = S3Hook(aws_conn_id = aws_conn_id)
        content = s3.read_key(bucket_name = bucket_name, key = key)
        return yaml.safe_load(content)
    
    @task()
    def read_csv_from_s3(config):
        for rule in config["configuration"]:
            if "output_file_location" in rule:
                r = rule["output_file_location"]
                bucket = r["bucket_name"]
                path = r["file_path"]
                fname = r["file_name"]
                key = os.path.join(path, fname)
                s3 = S3Hook(r['aws_conn_id'])
                content = s3.read_key(bucket_name = bucket, key = key)
                df = pd.read_csv(StringIO(content))
                return df.to_json(orient = "records")

    @task()
    def upload_to_postgres(df_json, config):
        df = pd.read_json(df_json)

        pg_config = None
        for rule in config["configuration"]:
            if "postgres_schema" in rule:
                pg_config = rule['postgres_schema']
                break

        conn = BaseHook.get_connection(pg_config["connection_id"])

        postgres_uri = conn.get_uri()
        postgres_uri = postgres_uri.replace("postgres://", "postgresql://")
        engine = create_engine(postgres_uri)

        column_definitions = []

        for col in pg_config["schema"]:
            column_name = col["name"]
            column_type = col["type"]
            column_definitions.append(f"{column_name} {column_type}")
        
        columns_sql = ", ".join(column_definitions)

        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {pg_config['table']} (
            {columns_sql}
        );
        """

        with engine.begin() as con:
            con.execute(text(create_table_sql))

            # upsert_config = None
            # try:
            #     for rule in config["configuration"]:
            #         if "upsert" in rule:
            #             upsert_config = rule['upsert']
            #             break
            # except:
            #     print()
            
            # if upsert_config:
            #     conflict_keys = upsert_config.get("conflict_keys",[])
            #     update_columns = upsert_config.get("update_columns", [])

            #     df.to_sql(pg_config["table"], con, if_exists="append", index=False, method = "multi")

            #     if conflict_keys and update_columns:
            #         conflict_keys_str = ", ".join(conflict_keys)
            #         update_columns_str = ", ".join([f"{col}=EXCLUDED.{col}" for col in update_columns])
            #         upsert_sql = f"""
            #         INSERT INTO {pg_config['table']} ({', '.join(df.columns)})
            #         VALUES ({', '.join(['%s']*len(df.columns))})
            #         ON CONFLICT ({conflict_keys_str}) DO UPDATE SET {update_columns_str};
            #         """
            # else:
            # Delete all existing data
            delete_sql = f"DELETE FROM {pg_config['table']};"
            con.execute(text(delete_sql))
            
            # Insert new data
            df.to_sql(pg_config['table'], con, if_exists="append", index=False, method="multi")

    cfg = read_config_from_s3()
    df_json = read_csv_from_s3(cfg)
    upload_to_postgres(df_json, cfg)

dag_main()
