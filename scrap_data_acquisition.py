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

DATASET = ["Linkedin", "Naukri", "FoundIt"]

@dag(
    dag_id = 'Scrap_dag_data_acquisition',
    schedule_interval = "0 0 * * *",
    start_date = datetime(2025, 9, 26),
    catchup = False,
    default_args = {
        'owner' : 'airflow',
        'retries' : 0,
        'retry_delay' :  timedelta(minutes= 2),
    },
    tags = ["Webscrap", "Linkedin", "Naukri"],
    default_view = "graph",
    description = "Stroring raw data"
)

def Scrap_dag():
    @task()
    def create_monday_folder():
        IST = timezone(timedelta(hours = 5, minutes = 30))
        today = datetime.now(IST)
        monday = today - timedelta(days=today.weekday())
        return monday.strftime("%Y%m%d")
    
    @task()
    def get_today_date():
        IST = timezone(timedelta(hours = 5, minutes = 30))
        today = datetime.now(IST)
        return today.strftime("%Y%m%d_%H")
    
    @task()
    def get_active_dataset():
        ctx = get_current_context()
        dataset = ctx["dag_run"].conf.get("dataset", "all")

        if dataset not in DATASET and dataset!="all":
            raise ValueError(f"Invalid dataset parameter {dataset}")
        if dataset == "all":
            active_ds = DATASET[:]
        else:
            active_ds = [dataset]
        return active_ds
    

    @task()
    def read_parafile(active_ds):
        pp={}

        bucket_name = "webscrap-bucket-store"
        aws_conn_id = "webscrap_bucket_s3_conn"
        s3 = S3Hook(aws_conn_id=aws_conn_id)

        for data in active_ds: 
            key = f"configuration/{data}/PipelineParameters/acquisition_parameter_{data}.json"
            logging.info(f"[read_parafile] Looking for key: {key}")

            try:
                if not s3.check_for_key(key=key, bucket_name=bucket_name):
                    logging.error(f"[read_parafile] Key not found in bucket: {bucket_name}/{key}")
                    continue

                content = s3.read_key(bucket_name=bucket_name, key=key)
                pp[data] = json.loads(content)
                logging.info(f"[read_parafile] Successfully loaded parameters for {data}")

            except Exception as e:
                logging.exception(f"[read_parafile] Failed reading key: {bucket_name}/{key} | Error: {str(e)}")

        logging.info(f"[read_parafile] Completed. Loaded configs for: {list(pp.keys())}")
        return pp
    
    @task()
    def schema_validation(active_ds, pp):
        errors = {}

        for data in active_ds:
            try:
                file_path = os.path.join(
                    pp[data]["file_location"],
                    pp[data]["file_name"]+pp[data]["file_extension"]
                )

                if not os.path.exists(file_path):
                    errors[data] = [f"File not found {file_path}"]
                    continue

                df = pd.read_csv(file_path)
                expected_schema = pp[data]["schema"]

                dataset_error = []
                for col, data_type in expected_schema.items():
                    if col not in df.columns:
                        dataset_error.append(f"Missing column: {col}")
                    else:
                        if str(df[col].dtype) != data_type:
                            dataset_error.append(f"Column {col} has {df[col].dtype}, expected {data_type}")     
                
                null_fails_col = pp[data]["validation_rules"]
                for col in null_fails_col:
                    if col in df.columns:
                        null_count = df[col].isnull().sum()
                        if null_count > 0:
                            dataset_error.append(f"Found null values in {col}") 
                
                if pp[data]["no_of_fields_check"].lower() == "true":
                    expected_column = len(expected_schema)
                    actual_column = df.shape[1]

                    if actual_column != expected_column:
                        dataset_error.append(f"Number of columns mismatch: expected {expected_column}, actual_column {actual_column}")
                
                if pp[data].get("p_missing_check", "false").lower() == "true":
                    missing_percentage = df.isnull().sum().sum() / (df.shape[0]*df.shape[1]) * 100
                    if missing_percentage > 20:
                        dataset_error.append(f"Total missing values {missing_percentage:.2f}% exceeds 20%")
                            
                if dataset_error:
                    errors[data] = dataset_error
                else:
                    errors[data] = []
            
            except Exception as e:
                logging.error(traceback.format_exc())
                errors[data] = [f"Unexpected error: {str(e)}"]
            

        return errors

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def report_errors(errors: dict):
        """Send email if validation errors exist"""
        if errors:
            msg = "<h3>Schema Validation Errors</h3><ul>"
            for dataset, errs in errors.items():
                msg += f"<li><b>{dataset}</b><ul>"
                for err in errs:
                    msg += f"<li>{err}</li>"
                msg += "</ul></li>"
            msg += "</ul>"

            return msg  # push to XCom
        return None

    send_email = EmailOperator(
        task_id="send_email",
        to="nishantsingh27022004@gmail.com",
        subject="Schema Validation Failed - Scrap DAG",
        html_content="{{ ti.xcom_pull(task_ids='report_errors') }}",
        trigger_rule=TriggerRule.ALL_DONE
    )

    @task()
    def upload_to_s3 (processing_week, today_date, active_ds, pp):

        bucket_name = "webscrap-bucket-store"
        aws_conn_id = "webscrap_bucket_s3_conn"
        s3 = S3Hook(aws_conn_id = aws_conn_id)

        logging.info(f"[upload_to_s3] Starting upload. Processing week={processing_week}, today={today_date}")
        logging.info(f"[upload_to_s3] Using bucket: {bucket_name}, connection: {aws_conn_id}")

        for data in active_ds:
            local_path = os.path.join(
                pp[data]["file_location"],
                pp[data]["file_name"]+pp[data]["file_extension"]
            )

            file_name = pp[data]["storing_file_name"].format(today = today_date)
            file_loc = pp[data]["storing_loc"].format(processing_week = processing_week)
            output_key = f"{file_loc}{file_name}"

            logging.info(f"[upload_to_s3] Dataset={data} | Local path={local_path} | S3 key={output_key}")

            s3.load_file(
                filename = local_path,
                key = output_key,
                bucket_name = bucket_name,
                replace = True
            )

            logging.info(f"[upload_to_s3] Successfully uploaded {local_path} -> s3://{bucket_name}/{output_key}")



    send_success_email = EmailOperator(
        task_id="send_success_email",
        to='nishantsingh27022004@gmail.com',   
        subject="✅ Webscrap DAG Data Acquisition Success",
        html_content="""
        <h3>DAG Run Completed Successfully!</h3>
        <p>All weather datasets have been processed and stored correctly.</p>
        """,
        trigger_rule=TriggerRule.ALL_SUCCESS
    )

    send_failure_email = EmailOperator(
    task_id='send_failure_email',
    to='nishantsingh27022004@gmail.com',
    subject='❌ Webscrap DAG Data Acquisition Failed!',
    html_content="""
        <h2 style="color:red;">Weather Data Acquisition Pipeline Failure</h2>
        <p><b>DAG:</b> weather_dag</p>
        <p><b>Execution Time:</b> {{ execution_date }}</p>
        <p>One or more tasks in the <b>weather_dag</b> have failed.</p>
        <p>Please review the logs in the Airflow UI for details.</p>
        <br>
        <p><b>Run ID:</b> {{ run_id }}</p>
        <p><b>Failed Task:</b> {{ task_instance.task_id }}</p>
        <p><b>Try Number:</b> {{ task_instance.try_number }}</p>
        <hr>
        <p style="font-size:13px;color:gray;">Visit the <a href="{{ ti.log_url }}">Airflow Logs</a> for this task.</p>
    """,
    trigger_rule=TriggerRule.ONE_FAILED
    )

    processing_week = create_monday_folder()
    today_date = get_today_date()
    active_ds = get_active_dataset()
    pp = read_parafile(active_ds)
    errors = schema_validation(active_ds, pp)
    msg = report_errors(errors)

    msg >> send_email

    upload_to_s3(processing_week, today_date, active_ds, pp) >> [send_success_email, send_failure_email]

Scrap_dag()



    
    