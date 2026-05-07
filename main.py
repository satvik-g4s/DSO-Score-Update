import streamlit as st
import pandas as pd
import numpy as np
import psycopg2
import time
from supabase import create_client

st.set_page_config(layout="wide")

st.title("DSO Score Upload")

uploaded_file = st.file_uploader(
    "Upload CSV File",
    type=["csv"]
)

st.caption("Required Columns: Cluster, Customer Code, DSO")

selected_date = st.date_input("Select Date (Select any date in the month of current DSO)")

run = st.button("Run")

log_container = st.container()

if run:

    with log_container:
        status_text = st.empty()

        if uploaded_file is None:
            st.error("Please upload the CSV file.")
            st.stop()

        try:
            status_text.info("Initializing Supabase connection...")
            time.sleep(0.5)

            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]

            supabase = create_client(url, key)

        except Exception as e:
            st.error(f"Error connecting to Supabase: {e}")
            st.stop()

        try:
            status_text.info("Preparing date variables...")
            time.sleep(0.5)

            date_variable = pd.to_datetime(selected_date)

            monthh = date_variable.month
            yearr = date_variable.year

            new_col = f"DSO_{monthh}_{yearr}"
            bucket_col = f"Bucket_{monthh}_{yearr}"
            impact_col = f"Impact_{monthh}_{yearr}"

        except Exception as e:
            st.error(f"Error preparing date variables: {e}")
            st.stop()

        try:
            status_text.info("Fetching existing records from Supabase...")

            all_rows = []

            for start in range(0, 100000, 1000):

                response = (
                    supabase
                    .table("DSO_SCORE")
                    .select('"key","Bucket_12_2025","Total Score"')
                    .range(start, start + 999)
                    .execute()
                )

                if not response.data:
                    break

                all_rows.extend(response.data)

            sql_df = pd.DataFrame(all_rows)

        except Exception as e:
            st.error(f"Error fetching data from Supabase: {e}")
            st.stop()

        try:
            status_text.info("Reading uploaded CSV file...")
            time.sleep(0.5)

            DSO = pd.read_csv(uploaded_file, index_col=False)

        except Exception as e:
            st.error(f"Error reading CSV file: {e}")
            st.stop()

        try:
            status_text.info("Validating required columns...")
            time.sleep(0.5)

            required_columns = [
                "Cluster",
                "Customer Code",
                "DSO"
            ]

            missing_columns = [
                col for col in required_columns
                if col not in DSO.columns
            ]

            if missing_columns:
                st.error(f"Missing columns: {missing_columns}")
                st.stop()

        except Exception as e:
            st.error(f"Error during column validation: {e}")
            st.stop()

        try:
            status_text.info("Cleaning and preparing DSO data...")
            time.sleep(0.5)

            DSO["Customer Code"] = DSO["Customer Code"].astype(int).astype(str)
            DSO["Cluster"] = DSO["Cluster"].astype(str)

            DSO["key"] = DSO["Customer Code"] + DSO["Cluster"]

            DSO.rename(columns={"DSO": new_col}, inplace=True)

            DSO = DSO[["key", new_col]]

        except Exception as e:
            st.error(f"Error during DSO preprocessing: {e}")
            st.stop()

        try:
            status_text.info("Merging data...")
            time.sleep(0.5)

            sql_df = pd.merge(
                sql_df,
                DSO,
                on="key",
                how="left"
            )

        except Exception as e:
            st.error(f"Error during merge: {e}")
            st.stop()

        try:
            status_text.info("Creating DSO buckets...")
            time.sleep(0.5)

            def create_bucket(dso):

                if pd.isna(dso):
                    return None

                elif dso <= 45:
                    return "< 45 days"

                elif dso <= 60:
                    return "46-60 days"

                elif dso <= 90:
                    return "61-90 days"

                else:
                    return "> 90 days"

            sql_df[bucket_col] = sql_df[new_col].apply(create_bucket)

        except Exception as e:
            st.error(f"Error while creating buckets: {e}")
            st.stop()

        try:
            status_text.info("Calculating impact scores...")
            time.sleep(0.5)

            def calculate_impact(old_bucket, new_bucket):

                impact_matrix = {

                    ("< 45 days", "< 45 days"): 5,
                    ("< 45 days", "46-60 days"): -20,
                    ("< 45 days", "61-90 days"): -50,
                    ("< 45 days", "> 90 days"): -75,

                    ("46-60 days", "< 45 days"): 5,
                    ("46-60 days", "46-60 days"): 0,
                    ("46-60 days", "61-90 days"): -50,
                    ("46-60 days", "> 90 days"): -75,

                    ("61-90 days", "< 45 days"): 50,
                    ("61-90 days", "46-60 days"): 5,
                    ("61-90 days", "61-90 days"): -20,
                    ("61-90 days", "> 90 days"): -75,

                    ("> 90 days", "< 45 days"): 75,
                    ("> 90 days", "46-60 days"): 50,
                    ("> 90 days", "61-90 days"): 0,
                    ("> 90 days", "> 90 days"): -75,
                }

                return impact_matrix.get((old_bucket, new_bucket), None)

            old_bucket = "Bucket_12_2025"

            sql_df[impact_col] = sql_df.apply(
                lambda row: calculate_impact(
                    row[old_bucket],
                    row[bucket_col]
                ),
                axis=1
            )

        except Exception as e:
            st.error(f"Error calculating impact scores: {e}")
            st.stop()

        try:
            status_text.info("Updating total scores...")
            time.sleep(0.5)

            sql_df["Total Score"] = (
                sql_df["Total Score"] + sql_df[impact_col]
            )

        except Exception as e:
            st.error(f"Error updating total score: {e}")
            st.stop()

        try:
            status_text.info("Formatting output columns...")
            time.sleep(0.5)

            sql_df = sql_df.replace({np.nan: None})

            sql_df[impact_col] = (
                sql_df[impact_col]
                .fillna(0)
                .astype(int)
            )

            sql_df["Total Score"] = (
                sql_df["Total Score"]
                .fillna(0)
                .astype(int)
            )

            sql_df[new_col] = (
                pd.to_numeric(
                    sql_df[new_col],
                    errors="coerce"
                )
            )

            sql_df[bucket_col] = (
                sql_df[bucket_col]
                .fillna("")
                .astype(str)
            )

        except Exception as e:
            st.error(f"Error formatting columns: {e}")
            st.stop()

        try:
            status_text.info("Connecting to Database...")
            time.sleep(0.5)

            conn = psycopg2.connect(
                host=st.secrets["PG_HOST"],
                database=st.secrets["PG_DATABASE"],
                user=st.secrets["PG_USER"],
                password=st.secrets["PG_PASSWORD"],
                port=st.secrets["PG_PORT"]
            )

            cur = conn.cursor()

            status_text.success("Connected to Database")
            time.sleep(0.5)

        except Exception as e:
            st.error(f"Error connecting to Database: {e}")
            st.stop()

        try:
            status_text.info("Creating columns if not exists...")
            time.sleep(0.5)

            query = f'''
            ALTER TABLE "DSO_SCORE"
            ADD COLUMN IF NOT EXISTS "{new_col}" NUMERIC;

            ALTER TABLE "DSO_SCORE"
            ADD COLUMN IF NOT EXISTS "{bucket_col}" TEXT;

            ALTER TABLE "DSO_SCORE"
            ADD COLUMN IF NOT EXISTS "{impact_col}" INTEGER;
            '''

            cur.execute(query)

            conn.commit()
            
            status_text.info("Waiting for columns to become available...")
            
            max_retries = 5
            retry_delay = 2
            
            for attempt in range(max_retries):
            
                try:
            
                    test_response = (
                        supabase
                        .table("DSO_SCORE")
                        .select(new_col)
                        .limit(1)
                        .execute()
                    )
            
                    break
            
                except Exception:
            
                    time.sleep(retry_delay)
            
                    if attempt == max_retries - 1:
                        raise
            
            status_text.success("Columns Created")
            
            time.sleep(0.5)

        except Exception as e:
            st.error(f"Error creating columns: {e}")
            cur.close()
            conn.close()
            st.stop()

        try:
            status_text.info("Preparing upload records...")
            time.sleep(0.5)

            records = sql_df[
                sql_df[new_col].notna()
            ][[
                "key",
                "Total Score",
                new_col,
                bucket_col,
                impact_col
            ]].to_dict(orient="records")

        except Exception as e:
            st.error(f"Error preparing upload records: {e}")
            cur.close()
            conn.close()
            st.stop()

        try:
            status_text.info("Uploading data to Database...")
            time.sleep(0.5)

            batch_size = 500

            progress_bar = st.progress(0)

            total_batches = max(1, len(range(0, len(records), batch_size)))

            current_batch = 0

            for i in range(0, len(records), batch_size):

                batch = records[i:i + batch_size]

                response = (
                    supabase
                    .table("DSO_SCORE")
                    .upsert(
                        batch,
                        on_conflict="key"
                    )
                    .execute()
                )

                current_batch += 1

                progress = current_batch / total_batches

                progress_bar.progress(progress)

                status_text.info(
                    f"Uploading Batch {current_batch} of {total_batches}"
                )
                time.sleep(0.5)

            status_text.success("Upload Complete")
            time.sleep(0.5)

        except Exception as e:
            st.error(f"Error during upload: {e}")
            cur.close()
            conn.close()
            st.stop()

        try:
            status_text.info("Closing database connection...")
            time.sleep(0.5)

            cur.close()

            time.sleep(5)

            conn.close()

            status_text.success("Connection Closed")
            time.sleep(0.5)

        except Exception as e:
            st.error(f"Error closing connection: {e}")
            st.stop()

        try:
            status_text.info("Preparing final download file...")
            time.sleep(0.5)
        
            all_download_rows = []
        
            for start in range(0, 100000, 1000):
        
                response = (
                    supabase
                    .table("DSO_SCORE")
                    .select("*")
                    .range(start, start + 999)
                    .execute()
                )
        
                if not response.data:
                    break
        
                all_download_rows.extend(response.data)
        
            download_df = pd.DataFrame(all_download_rows)
        
            if "Total Score" in download_df.columns:
        
                cols = [
                    col for col in download_df.columns
                    if col != "Total Score"
                ] + ["Total Score"]
        
                download_df = download_df[cols]
        
                download_df = download_df.sort_values(
                    by="Total Score",
                    ascending=False
                )
        
            csv_output = download_df.to_csv(index=False).encode("utf-8")
        
            status_text.success("Final Report Ready")
        
            st.download_button(
                label="Download Report",
                data=csv_output,
                file_name="dso_score_output.csv",
                mime="text/csv"
            )
        
        except Exception as e:
            st.error(f"Error preparing download file: {e}")
            st.stop()

with st.expander("What This Tool Does"):

    st.markdown("""
    - Uploads latest customer DSO data
    - Creates DSO bucket classifications
    - Calculates customer movement impact
    - Updates total score values
    - Pushes updated records into Supabase
    """)

with st.expander("How to Use"):

    st.markdown("""
    1. Upload the CSV input file
    2. Ensure required columns are available
    3. Select the reporting date
    4. Click Run
    5. Download processed output after completion
    """)

with st.expander("Output Details"):

    st.markdown("""
    Output includes:

    - Customer key
    - Updated DSO value
    - New DSO bucket
    - Impact score
    - Updated Total Score
    """)

with st.expander("Financial Logic"):

    st.markdown("""
    ### Bucket Classification

    - < 45 days
    - 46–60 days
    - 61–90 days
    - > 90 days

    ### Impact Logic

    Customers moving to better buckets receive positive impact.

    Customers moving to worse buckets receive negative impact.

    ### Total Score Formula

    Total Score = Existing Total Score + Impact Score
    """)
