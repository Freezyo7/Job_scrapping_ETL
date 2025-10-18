from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.operators.python import get_current_context
from airflow.utils.trigger_rule import TriggerRule
from airflow.operators.email import EmailOperator
from datetime import datetime, timedelta, timezone
from airflow.decorators import dag, task
import pandas as pd
import requests
import json
import os
import logging
import traceback
from airflow.operators.python import BranchPythonOperator
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.decorators import dag, task
from datetime import datetime, timedelta, timezone
from airflow import DAG
from io import StringIO
import pandas as pd
import logging
import numpy as np
import pytz
import json
import yaml 
import os
import io


DATASET = ["Linkedin", "Naukri", "Foundit"]

@dag(
    dag_id = "webscrap_etl",
    schedule_interval = "40 11 * * *",
    start_date = datetime(2025, 10, 6),
    catchup = False,
    default_args = {
        'owner' : 'airflow',
        'retries' : 0,
        'retry_delay' : timedelta(minutes= 2) 
    },
    tags = ["extract", "transform", "load"],
    default_view = "graph",
    description = "transform raw data and merge them together weekly"
)

def etl_dag():
    @task()
    def get_today_date():
        IST = timezone(timedelta(hours = 5, minutes= 30))
        today = datetime.now(IST).strftime("%Y%m%d")
        return today

    @task()
    def get_processing_monday_date():
        IST = timezone(timedelta(hours = 5, minutes= 30))
        today = datetime.now(IST)
        monday = today - timedelta(days=today.weekday())
        return monday.strftime('"%Y%m%d')
    
    @task()
    def get_dataset_config_file():
        bucket_name = "webscrap-bucket-store"
        key = "dynamic/dataset_configuration.xlsx"
        aws_conn_id = "webscrap_bucket_s3_conn"

        s3 = S3Hook(aws_conn_id = aws_conn_id)
        obj = s3.get_key(bucket_name = bucket_name, key = key)
        content = obj.get()['Body'].read()
        ds = pd.read_excel(io.BytesIo(content),engine="openpyxl")
        return ds.to_dict(orient="records")
    
    @task()
    def get_active_dataset(dataset_config):
        df = pd.DataFrame(dataset_config)
        df['Status'] = df['Status'].astype(str).str.strip().str.lower()

        active_df = df[df['Status'] == 'active']
        return active_df.to_dict(orient = "records")
    
    @task()
    def get_etl_config_file(active_ds:dict):
        etl_info = {}

        bucket_name = "webscrap-bucket-store"
        aws_conn_id = "webscarp_bucket_s3_conn"

        s3 = S3Hook(aws_conn_id=aws_conn_id)

        for ds in active_ds:
            key = ds["ETL_file_path"]

            keys = s3.list_keys(bucket_name = bucket_name, prefix = key)

            if not keys:
                raise FileNotFoundError(f"❌ Key not found in bucket {bucket_name}: {key}")
            
            content = s3.read_key(bucket_name = bucket_name, key = keys)
            config = yaml.safe_load(content)
            etl_info[ds["Dataset"]] = config

        return etl_info
    
    @task()
    def etl(yml_file, processing_week, current_date):
        


