# How to connect a Cloud Composer environment to a Cloud SQL for PostgreSQL instance

These are basic steps that you can take to set up a [Cloud Composer][1] environment to a [Cloud SQL for PostgreSQL][2] instance, using the [Cloud SQL Proxy][3] and connecting via the instance's [private IP address][4].

> Note: Remember to replace any placeholders in the commands and configuration files. The placeholders in this guide all follow the format `<all_lowercase>`.

### 1. Enable the Composer API:
```
gcloud services enable composer.googleapis.com
```
#### (Optional) Set an env variable with the project ID, for convenience:
```
export PROJECT_ID=<project_id>
```
### 2. Create the Composer service account and give it the necessary IAM roles:
```
gcloud iam service-accounts create cloud-composer --display-name='Cloud Composer Service Account'
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:cloud-composer@$PROJECT_ID.iam.gserviceaccount.com --role=roles/composer.worker
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:cloud-composer@$PROJECT_ID.iam.gserviceaccount.com --role=roles/cloudsql.client
```
### 3. Create the Composer Environment:

```
gcloud composer environments create data-synchronization-env --location=<region> --zone=<zone> --service-account=cloud-composer@$PROJECT_ID.iam.gserviceaccount.com --python-version=3 --enable-ip-alias --enable-private-environment --web-server-allow-all
```
Check the [gcloud composer environments create][5] command documentation for more information about the available options.

### 4. Enable the [Service Networking API][6]:
```
gcloud services enable servicenetworking.googleapis.com
```
### 5. Create an IP address range for the creation of the VPC peering connection:
```
gcloud compute addresses create google-managed-services-default --global --purpose=VPC_PEERING --prefix-length=16 --network=default --project=$PROJECT_ID

gcloud services vpc-peerings connect --service=servicenetworking.googleapis.com --ranges=google-managed-services-default --network=default --project=$PROJECT_ID
```
### 6. Create the Cloud SQL for PostgreSQL instance:
```
gcloud beta sql instances create postgresql-instance-prod --zone=<zone> --no-assign-ip --database-version=POSTGRES_12 --tier=<instance_tier> --network=projects/$PROJECT_ID/global/networks/default
```
Check the [gcloud beta sql instances create][7] command documentation for more information on the available options.

### 7. Create a Cloud SQL user that will access the instance via the Cloud SQL Proxy:
```
gcloud sql users create proxyclient --host=cloudsqlproxy~% --instance=postgresql-instance-prod --password=<password>
```
### 8. Create a test database to test the connection:
```
gcloud sql databases create test --instance=postgresql-instance-prod
```
### 9. Configure kubectl for deploying to the cluster:
Get the cluster name created for the Composer Environment.
```
gcloud container clusters list
```

Configure **kubectl**.
```
gcloud container clusters get-credentials <cluster_name> --zone=<zone>
```

#### (Optional, if you are using the Cloud Shell) whitelist the Cloud Shell IP address

Get Cloud Shell IP Address.
```
dig +short myip.opendns.com @resolver1.opendns.com
```
Whitelist the IP address.
```
gcloud container clusters update <cluster_name> --zone <zone> --enable-master-authorized-networks --master-authorized-networks <cloud_shell_ip>/32
```

### 10. Create a `namespace.yaml` file:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: composer-cloudsql
  labels:
    name: composer-cloudsql
```
And create the namespace:
```
kubectl apply -f namespace.yaml
```
### 11. Created a `deployment.yaml` file:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    run: cloud-sql-proxy
  name: cloud-sql-proxy
  namespace: composer-cloudsql
spec:
  replicas: 1
  selector:
    matchLabels:
      run: cloud-sql-proxy
  strategy:
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 1
    type: RollingUpdate
  template:
    metadata:
      labels:
        run: cloud-sql-proxy
    spec:
      containers:
      - command:
        - /cloud_sql_proxy
        - -instances=<project_id>:<region>:<instance_id>=tcp:0.0.0.0:5432
        image: gcr.io/cloudsql-docker/gce-proxy
        imagePullPolicy: IfNotPresent
        name: airflow-sqlproxy
        ports:
        - containerPort: 5432
          protocol: TCP
        terminationMessagePath: /dev/termination-log
        terminationMessagePolicy: File
      nodeSelector:
        cloud.google.com/gke-nodepool: default-pool
      restartPolicy: Always
```
And create the deployment:
```
kubectl apply -f deployment.yaml
```
### 12. Create a `service.yaml` file:

```yaml
kind: Service
apiVersion: v1
metadata:
  labels:
    run: cloud-sql-proxy-service
  name: cloud-sql-proxy-service
  namespace: composer-cloudsql
spec:
  ports:
  - port: 5432
    protocol: TCP
    targetPort: 5432
  selector:
    run: cloud-sql-proxy
```
And create the service for the Cloud SQL Proxy:
```
kubectl apply -f service.yaml
```
### 13. Add the connection config to the Airflow UI:

> Note: Remove the available `postgres_default` connection, if you plan on using the proxy as the default method

The following fields of the UI form should be filled with the following information:

- **Conn Id**: postgres_default
- **Conn Type**: Postgres
- **Host**: cloud-sql-proxy-service.composer-cloudsql
- **Schema**: test
- **Login**: proxyclient
- **Port**: 5432

### 14. Create a python script called `test_dag.py`:

```py
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
```
Get the DAGs Google Cloud Storage bucket:
```
gcloud composer environments describe data-synchronization-env --location=<region>
```
Upload the script to the DAGs bucket:
```
gsutil cp ./test_dag.py gs://<bucket>/dags
```
### 15. Finally, trigger the job from the Airflow UI and confirm that it run successfully.

[1]: https://cloud.google.com/composer/docs/concepts/overview
[2]: https://cloud.google.com/sql/docs/postgres/quickstart
[3]: https://github.com/GoogleCloudPlatform/cloudsql-proxy
[4]: https://cloud.google.com/sql/docs/postgres/private-ip
[5]: https://cloud.google.com/sdk/gcloud/reference/composer/environments/create
[6]: https://cloud.google.com/service-infrastructure/docs/service-networking/getting-started
[7]: https://cloud.google.com/sdk/gcloud/reference/beta/sql/instances/create