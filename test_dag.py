from datetime import datetime
from airflow import DAG
from airflow.operators.postgres_operator import PostgresOperator

dag_params = {
    'dag_id': 'test_postgres_select',
    'start_date': datetime(2021, 1, 1),
    'schedule_interval': None,
    'description': 'Test connection to the Cloud SQL DB'
}

dag = DAG(**dag_params)

t1 = PostgresOperator(
    task_id='test_select_log_airflow',
    sql="SELECT 1;",
    dag=dag
)
