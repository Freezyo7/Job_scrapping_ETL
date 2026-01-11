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
import re


DATASET = ["Linkedin", "Naukri", "Foundit"]

def extract_date_from_filename(filename):

    if not isinstance(filename, str):
        logging.warning(f"[ETL] Filename is not a string: {type(filename)}")
        return None

    match = re.search(r'(\d{8})', filename)
    if match:
        return match.group(1)
    logging.warning(f"[ETL] Could not extract date from filename: {filename}")
    return None

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
    # @task()
    # def get_today_date():
    #     IST = timezone(timedelta(hours = 5, minutes= 30))
    #     today = datetime.now(IST).strftime("%Y%m%d")
    #     return today
    @task()
    def get_seven_day_window():
        IST = timezone(timedelta(hours=5, minutes=30))
        end_date = datetime.now(IST)
        start_date = end_date - timedelta(days=6)

        return {
            'start_date': start_date.strftime("%Y%m%d"),
            'end_date': end_date.strftime("%Y%m%d"),
        }

    # @task()
    # def get_processing_monday_date():
    #     IST = timezone(timedelta(hours = 5, minutes= 30))
    #     today = datetime.now(IST)
    #     monday = today - timedelta(days=today.weekday())
    #     return monday.strftime("%Y%m%d")

    @task()
    def get_processing_week_for_window(date_window):
        IST = timezone(timedelta(hours=5, minutes=30))

        start_date = datetime.strptime(date_window['start_date'], "%Y%m%d").replace(tzinfo=IST)
        end_date = datetime.strptime(date_window['end_date'], "%Y%m%d").replace(tzinfo=IST)

        processing_week = set()

        current = start_date

        while current <= end_date:
            monday = current - timedelta(days=current.weekday())
            processing_week.add(monday.strftime("%Y%m%d"))
            current +=timedelta(days=1)
        
        weeks_list = sorted(list(processing_week))
        logging.info(f"[WINDOW] Processing weeks for 7-day window: {weeks_list}")
        return weeks_list

    @task()
    def get_dataset_config_file():
        bucket_name = "webscrap-bucket-store"
        key = "Job_data/Automation/dynamic/dataset_configuration.xlsx"
        aws_conn_id = "webscrap_bucket_s3_conn"

        s3 = S3Hook(aws_conn_id = aws_conn_id)
        obj = s3.get_key(bucket_name = bucket_name, key = key)
        content = obj.get()['Body'].read()
        ds = pd.read_excel(io.BytesIO(content),engine="openpyxl")
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
        aws_conn_id = "webscrap_bucket_s3_conn"

        s3 = S3Hook(aws_conn_id=aws_conn_id)

        for ds in active_ds:
            dataset_name = ds["Dataset"]
            config_key = ds["ETL_file_path"]
            logging.info(f"[CONFIG] Loading: {dataset_name} from {config_key}")

            if not s3.check_for_key(key=config_key, bucket_name=bucket_name):
                raise FileNotFoundError(
                    f"❌ Config file not found: s3://{bucket_name}/{config_key}"
                )
            
            content = s3.read_key(bucket_name=bucket_name, key=config_key)
        
            if not content.strip():
                raise ValueError(f"❌ Config file is empty: {config_key}")

            config = yaml.safe_load(content)
            etl_info[dataset_name] = config

        return etl_info
    
    @task()
    def etl(yml_file, processing_week, date_window):

        result = {}
        all_final_df = []

        start_date_str = date_window['start_date']
        end_date_str = date_window['end_date']
        start_date_int = int(start_date_str)
        end_date_int = int(end_date_str)

        logging.info(f"[ETL] Processing 7-day window: {start_date_str} to {end_date_str}")
        logging.info(f"[ETL] Processing weeks: {processing_week}")

        
        for ds, info in yml_file.items():

            df_map = {} #data frame name

            for rule in info["transform_rules"]:
                rule_type = list(rule.keys())[0]
                rule_config = rule[rule_type]

                if rule_type == 'add_dataframe':
                    add_df_rule = rule_config
                    df_name = add_df_rule["dataframe"]
                    raw_file_path = add_df_rule['file_path']

                    s3 = S3Hook(aws_conn_id = "webscrap_bucket_s3_conn")
                    bucket_name = "webscrap-bucket-store"

                    all_dfs = []
                    file_hint = add_df_rule['file_name_hint']

                    weeks_checked = 0
                    weeks_with_data = 0
                    total_file_found = 0

                    for proc_week in processing_week:

                        weeks_checked += 1

                        resolved_path = raw_file_path.replace("{processing_week}", proc_week)
                        prefix = resolved_path

                        try:
                            all_keys = s3.list_keys(bucket_name=bucket_name, prefix=prefix) or []
                        except Exception as e:
                            logging.warning(
                                f"[ETL] ⚠️  Could not access s3://{bucket_name}/{prefix} - {str(e)}"
                            )
                            all_keys = []
                        
                        if not all_keys:
                            logging.warning(
                                f"[ETL] ⚠️  No files found in processing week {proc_week} "
                                f"at s3://{bucket_name}/{prefix}"
                            )
                            continue

                        logging.info(f"[ETL] ✓ Found {len(all_keys)} keys in week {proc_week}")
                        weeks_with_data += 1

                        csv_keys = []
                        for key in all_keys:
                            if key.endswith(".csv"):
                                csv_keys.append(key)

                        for csv in csv_keys:
                            file_date_str = extract_date_from_filename(csv)

                            if not file_date_str:
                                logging.warning(f"[ETL] Skipping file (no date found): {csv}")
                                continue

                            file_date_int = int(file_date_str)

                            if start_date_int <= file_date_int <= end_date_int:

                                if file_hint and file_hint not in csv:
                                    continue
                                logging.info(f"[ETL] ✅ Including file: {csv} (date: {file_date_str})")

                                try:
                                    obj = s3.read_key(bucket_name=bucket_name, key=csv)
                                    if not obj.strip():
                                        logging.warning(f"[ETL] Skipping empty file: {csv}")
                                        continue
                                    df = pd.read_csv(StringIO(obj))
                                    all_dfs.append(df)
                                    total_file_found += 1
                                
                                except Exception as e:
                                    logging.error(f"[ETL] Error reading {csv}: {str(e)}")
                                    continue
                            else:
                                logging.info(f"[ETL] ⏭️  Skipping file (outside window): {csv} (date: {file_date_str})")
                        
                    if not all_dfs:
                        logging.warning(
                            f"[ETL] No CSV files found for {ds} in 7-day window "
                            f"({start_date_str} to {end_date_str})"
                        )
                        # You can either raise an error or continue with empty df
                        # raise ValueError(f"No data found for {ds} in 7-day window")
                        continue
                    
                    compiled_df = pd.concat(all_dfs, ignore_index=True)
                    df_map[df_name] = compiled_df
                    logging.info(
                        f"[ETL] ✅ Combined {len(all_dfs)} files for {df_name} "
                        f"({len(compiled_df)} total records)"
                        )

                    continue
            
            for rule in info['transform_rules']:
                rule_type = list(rule.keys())[0]
                rule_config = rule[rule_type]

                if rule_type == "add_dataframe":
                    continue

                elif rule_type == 'dropna':
                    df_name = rule_config['dataframe']

                    if df_name not in df_map:
                        raise KeyError(f"Dataframe '{df_name}' not found for drop_na")
                    subset = rule_config['subset']
                    how = rule_config['how']

                    df_map[df_name] = df_map[df_name].dropna(subset=subset, how=how)

                elif rule_type == 'date_formatting':
                    df_name = rule_config['dataframe']

                    tz = rule_config.get("timezone", "Asia/Kolkata")

                    columns = rule_config['columns']

                    for col in columns:
                        source_col = col['source']
                        target_col = col['target']
                        input_fmt = col['input_format']
                        output_fmt = col['output_format']
                        series = pd.to_datetime(
                            df_map[df_name][source_col],
                            format=input_fmt,      # STRING parsing
                            errors="coerce"
                        )

                        if tz:
                            series = series.dt.tz_localize(tz, nonexistent="NaT", ambiguous="NaT")

                        if output_fmt:
                            series = series.dt.strftime(output_fmt)

                        df_map[df_name][target_col] = series
                
                elif rule_type == 'type_casting':
                    df_name = rule_config['dataframe']

                    columns = rule_config['dtype_mapping']

                    for col, val in columns.items():
                        df_map[df_name][col] = df_map[df_name][col].astype(val)

                elif rule_type == 'handle_missing':
                    df_name = rule_config['dataframe']
                    
                    # Validate dataframe exists
                    if df_name not in df_map:
                        raise KeyError(f"Dataframe '{df_name}' not found for handle_missing")
                    
                    method = rule_config['method']
                    
                    if method == 'fill':
                        fill_value = rule_config.get('fill_value', {})
                        
                        if not fill_value:
                            raise ValueError(f"fill_value is required for method 'fill'")
                        
                        if isinstance(fill_value, dict):
                            # Column-specific fill values (YOUR CASE)
                            for col, val in fill_value.items():
                                if col in df_map[df_name].columns:
                                    # Count missing values before filling
                                    missing_count = df_map[df_name][col].isna().sum()
                                    
                                    # Fill missing values
                                    df_map[df_name][col] = df_map[df_name][col].fillna(val)
                                    
                                    logging.info(
                                        f"[ETL] Filled {missing_count} missing values in column '{col}' "
                                        f"with value '{val}'"
                                    )
                                else:
                                    logging.warning(
                                        f"[ETL] Column '{col}' not found in dataframe '{df_name}'. "
                                        f"Available columns: {list(df_map[df_name].columns)}"
                                    )
                        else:
                            raise ValueError(
                                f"fill_value must be a dictionary for column-specific fills. "
                                f"Got: {type(fill_value)}"
                            )
                    
                    else:
                        raise ValueError(
                            f"Unknown handle_missing method: '{method}'. "
                            f"Currently only 'fill' method is supported."
                            )
                    
                elif rule_type == "drop_columns":
                    df_name = rule_config['dataframe']
                    columns = rule_config['columns']

                    df_map[df_name].drop(columns = columns, inplace=True, errors = 'ignore')
                
                elif rule_type == "regex_replace":
                    df_name = rule_config['dataframe']
                    clm = rule_config['columns']
                    pattern = rule_config['pattern']
                    replacement = rule_config['replacement']

                    if clm not in df_map[df_name].columns:
                        raise KeyError(
                            f"Column '{clm}' not found in dataframe '{df_name}'. "
                            f"Available columns: {list(df_map[df_name].columns)}"
                            )
                    
                elif rule_type == "drop_duplicate":
                    df_name = rule_config['dataframe']
                    keep = rule_config.get('keep',"")
                    subset = rule_config.get('subset', "")

                    if subset:
                        if isinstance(subset, str):
                            subset = [subset]
                            subset = [col for col in subset if col in df_map[df_name].columns]
                            if not subset:
                                subset = None

                    df_map[df_name].drop_duplicates(keep=keep, subset=subset)

                elif rule_type == "renaming_columns":
                    df_name = rule_config['dataframe']
                    
                    if df_name not in df_map:
                        raise KeyError(f"Dataframe '{df_name}' not found for renaming_columns")
                    
                    rename_mapping = rule_config.get('columns', {})
                    
                    # Debug: Print what we received
                    logging.info(f"[ETL DEBUG] Renaming columns in '{df_name}'")
                    logging.info(f"[ETL DEBUG] Rename mapping from YAML: {rename_mapping}")
                    logging.info(f"[ETL DEBUG] Current columns: {list(df_map[df_name].columns)}")
                    
                    # Skip if no columns specified
                    if not rename_mapping:
                        logging.warning(f"[ETL] No columns specified for renaming in '{df_name}', skipping")
                        continue
                    
                    # Validate it's a dictionary
                    if not isinstance(rename_mapping, dict):
                        raise ValueError(
                            f"'columns' must be a dictionary for renaming_columns. "
                            f"Got: {type(rename_mapping).__name__} - Value: {rename_mapping}"
                        )
                    
                    # Only rename columns that exist
                    existing_renames = {
                        old: new for old, new in rename_mapping.items() 
                        if old in df_map[df_name].columns
                    }
                    
                    # Debug: Show what will be renamed
                    logging.info(f"[ETL DEBUG] Columns that will be renamed: {existing_renames}")
                    
                    if existing_renames:
                        df_map[df_name].rename(columns=existing_renames, inplace=True)
                        logging.info(f"✅ [ETL] Renamed columns in '{df_name}': {existing_renames}")
                        logging.info(f"[ETL DEBUG] Columns after rename: {list(df_map[df_name].columns)}")
                    else:
                        logging.warning(
                            f"❌ [ETL] None of the columns to rename exist in '{df_name}'. "
                            f"Expected: {list(rename_mapping.keys())}, "
                            f"Available: {list(df_map[df_name].columns)}"
                        )
                        
                        # Show which columns are missing
                        missing = [col for col in rename_mapping.keys() if col not in df_map[df_name].columns]
                        logging.warning(f"[ETL DEBUG] Missing columns: {missing}")

                elif rule_type == "reorder_columns":
                    df_name = rule_config["dataframe"]

                    column_order = rule_config['columns']
                    reordered_columns = []
                    for col in column_order:
                        if col in df_map[df_name].columns:
                            reordered_columns.append(col)
                    df_map[df_name] = df_map[df_name][reordered_columns]

            # for df_name, df in df_map.items():
            #     file_name = f'etl{ds}_job_data.csv'
            #     local_path = os.path.join("/tmp", file_name)
            #     df.to_csv(local_path, index = False)
            #     result[ds] = local_path
            if df_map:
                final_df = list(df_map.values())[0]
                final_df['source_dataset'] = ds
                all_final_df.append(final_df)

        if not all_final_df:
            raise ValueError("No dataframe available")
        
        final_df = pd.concat(all_final_df, ignore_index=True)
        final_df = final_df.drop_duplicates(
            subset=["job_title", "company_name"],
            keep="first")
        
        file_name = "main_output.csv"
        local_path = os.path.join("/tmp", file_name)
        final_df.to_csv(local_path, index = False)

        result["FINAL"] = local_path

        
        return result
    
    @task
    def store_transformed_data (result, date_window, active_dataset_config):
        s3 = S3Hook(aws_conn_id="webscrap_bucket_s3_conn")

        local_path = result.get("FINAL")
        if not local_path:
            raise ValueError("No final transformed file found")
        
        start_date = date_window['start_date']
        end_date = date_window['end_date']

        output_path = "Job_data/Output/"
        file_name = "all_job_data.csv"
        output_key = f"{output_path}{file_name}"

        s3.load_file(
            filename=local_path,
            key=output_key,
            bucket_name="webscrap-bucket-store",
            replace=True
        )

        os.remove(local_path)

        return output_key
    
        # s3 = S3Hook(aws_conn_id = "webscrap_bucket_s3_conn")
        # uploaded_files = []

        # for info in active_dataset_config:
        #     dataset = info['Dataset']
        #     local_path = result.get(dataset)
        #     if not local_path:
        #         raise ValueError(f"No transformed data present here {dataset}")
            
        #     file_name = info['Output_file_name']
        #     output_path = info["Output_path"].replace("{processing_week}", processing_week)
        #     output_key = f"{output_path}{file_name}"

        #     s3.load_file(
        #         filename = local_path,
        #         key = output_key,
        #         bucket_name = "webscrap-bucket-store",
        #         replace = True
        #         )
        #     os.remove(local_path)
        #     uploaded_files.append(output_key)

        # return uploaded_files
    
    send_success_email = EmailOperator(
        task_id='send_success_email',
        to='nishantsingh27022004@gmail.com',
        subject='✅ Weather DAG ETL Succeeded!',
        html_content="""
            <h2 style="color:green;">Weather Data Acquisition Pipeline Success</h2>
            <p><b>DAG:</b> weather_dag</p>
            <p><b>Execution Time:</b> {{ execution_date }}</p>
            <p><b>Generated CSV Files:</b></p>
            <ul>
            {% set files = ti.xcom_pull(task_ids='etl_transformation') %}
            {% for ds, path in files.items() %}
                <li><b>{{ ds }}</b>: {{ path.split('/')[-1] }} (Local: {{ path }})</li>
            {% endfor %}
            </ul>
            <p><b>S3 Upload Folder:</b> {{ ti.xcom_pull(task_ids='store_transformed_data') or 'Unknown' }}</p>
            <br>
            <p style="font-size:14px;">Check your S3 bucket for the updated weather data.</p>
            <hr>
            <p style="font-size:13px;color:gray;">Airflow DAG Run ID: {{ run_id }}</p>
        """,
        trigger_rule=TriggerRule.ALL_SUCCESS
        )

    send_failure_email = EmailOperator(
        task_id='send_failure_email',
        to='nishantsingh27022004@gmail.com',
        subject='❌ Weather DAG ETL Failed!',
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

    # current_date = get_today_date()
    date_window = get_seven_day_window()
    processing_week = get_processing_week_for_window(date_window)
    dataset_config = get_dataset_config_file()
    active_dataset = get_active_dataset(dataset_config)
    yml_file = get_etl_config_file(active_dataset)
    result = etl(yml_file, processing_week, date_window)
    upload = store_transformed_data(result, date_window, active_dataset)

    upload >> [send_failure_email, send_success_email]

etl_dag()



            







