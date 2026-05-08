import streamlit as st
import pandas as pd
import numpy as np
import psycopg2
import time
from supabase import create_client
import streamlit_ant_design_components as sac


st.set_page_config(layout="wide")

st.title("DSO Score Upload")

uploaded_file = st.file_uploader(
    "Upload CSV File",
    type=["csv"]
)

st.caption("Required Columns: Cluster, Customer Code, DSO")

selected_month = sac.date_picker(
    label='Select Month',
    picker='month'
)

run = st.button("Run")

log_container = st.container()


# =========================
# HELPER FUNCTIONS
# =========================

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

    return impact_matrix.get((old_bucket, new_bucket), 0)


def calculate_range(old_bucket, current_dso):

    if pd.isna(current_dso):
        return ""

    if old_bucket == "< 45 days":

        if current_dso < 46:
            return "In Range"

        elif current_dso < 61:
            return "Mid Range"

        else:
            return "Out Range"

    elif old_bucket == "46-60 days":

        if current_dso < 61:
            return "In Range"

        elif current_dso < 91:
            return "Mid Range"

        else:
            return "Out Range"

    elif old_bucket == "61-90 days":

        if current_dso < 91:
            return "In Range"

        else:
            return "Out Range"

    elif old_bucket == "> 90 days":
        return "In Range"

    return ""


# =========================
# MAIN APP
# =========================

if run:

    with log_container:

        status_text = st.empty()

        if uploaded_file is None:
            st.error("Please upload the CSV file.")
            st.stop()

        # =========================
        # SUPABASE CONNECTION
        # =========================

        try:

            status_text.info("Initializing Supabase connection...")
            time.sleep(0.2)

            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]

            supabase = create_client(url, key)

        except Exception as e:

            st.error(f"Error connecting to Supabase: {e}")
            st.stop()

        # =========================
        # DATE VARIABLES
        # =========================

        try:

            status_text.info("Preparing date variables...")
            time.sleep(0.2)

            date_variable = pd.to_datetime(selected_date)

            monthh = date_variable.month
            yearr = date_variable.year

            new_col = f"DSO_{monthh}_{yearr}"
            impact_col = f"Impact_{monthh}_{yearr}"

        except Exception as e:

            st.error(f"Error preparing date variables: {e}")
            st.stop()

        # =========================
        # FETCH DATABASE
        # =========================

        try:

            status_text.info("Fetching existing records from Database...")

            all_rows = []

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

                all_rows.extend(response.data)

            sql_df = pd.DataFrame(all_rows)

        except Exception as e:

            st.error(f"Error fetching data from Database: {e}")
            st.stop()

        # =========================
        # READ CSV
        # =========================

        try:

            status_text.info("Reading uploaded CSV file...")
            time.sleep(0.2)

            DSO = pd.read_csv(uploaded_file, index_col=False)

        except Exception as e:

            st.error(f"Error reading CSV file: {e}")
            st.stop()

        # =========================
        # VALIDATE COLUMNS
        # =========================

        try:

            status_text.info("Validating required columns...")
            time.sleep(0.2)

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

        # =========================
        # CLEAN INPUT
        # =========================

        try:

            status_text.info("Cleaning and preparing DSO data...")
            time.sleep(0.2)

            DSO["Customer Code"] = (
                DSO["Customer Code"]
                .astype(int)
                .astype(str)
            )

            DSO["Cluster"] = (
                DSO["Cluster"]
                .astype(str)
            )

            DSO["key"] = (
                DSO["Customer Code"] +
                DSO["Cluster"]
            )

            DSO.rename(
                columns={"DSO": new_col},
                inplace=True
            )

            DSO = DSO[["key", new_col]]

        except Exception as e:

            st.error(f"Error during preprocessing: {e}")
            st.stop()

        # =========================
        # FIND PREVIOUS DSO COLUMN
        # =========================
        previous_dso_col="DSO_12_2025"

        # =========================
        # MERGE
        # =========================

        try:

            status_text.info("Merging data...")
            time.sleep(0.2)

            sql_df = pd.merge(
                sql_df,
                DSO,
                on="key",
                how="left"
            )

        except Exception as e:

            st.error(f"Error during merge: {e}")
            st.stop()

        # =========================
        # TEMP BUCKETS
        # =========================

        try:

            status_text.info("Calculating movement impact...")
            time.sleep(0.2)

            temp_old_bucket = "temp_old_bucket"
            temp_new_bucket = "temp_new_bucket"

            sql_df[temp_new_bucket] = (
                sql_df[new_col]
                .apply(create_bucket)
            )

            if previous_dso_col:

                sql_df[temp_old_bucket] = (
                    sql_df[previous_dso_col]
                    .apply(create_bucket)
                )

            else:

                sql_df[temp_old_bucket] = None

            sql_df[impact_col] = sql_df.apply(
                lambda row: calculate_impact(
                    row[temp_old_bucket],
                    row[temp_new_bucket]
                ),
                axis=1
            )

        except Exception as e:

            st.error(f"Error calculating impact: {e}")
            st.stop()

        # =========================
        # UPDATE SCORE
        # =========================

        try:

            status_text.info("Updating total scores...")
            time.sleep(0.2)

            sql_df["Total Score"] = (
                sql_df["Total Score"]
                .fillna(0)
                .astype(int)
            )

            sql_df[impact_col] = (
                sql_df[impact_col]
                .fillna(0)
                .astype(int)
            )

            sql_df["Total Score"] = (
                sql_df["Total Score"] +
                sql_df[impact_col]
            )

        except Exception as e:

            st.error(f"Error updating total score: {e}")
            st.stop()

        # =========================
        # FORMAT
        # =========================

        try:

            status_text.info("Formatting data...")
            time.sleep(0.2)

            sql_df[new_col] = (
                pd.to_numeric(
                    sql_df[new_col],
                    errors="coerce"
                )
            )

            sql_df = sql_df.replace({np.nan: None})

        except Exception as e:

            st.error(f"Error formatting data: {e}")
            st.stop()

        # =========================
        # CONNECT POSTGRES
        # =========================

        try:

            status_text.info("Connecting to Database...")
            time.sleep(0.2)

            conn = psycopg2.connect(
                host=st.secrets["PG_HOST"],
                database=st.secrets["PG_DATABASE"],
                user=st.secrets["PG_USER"],
                password=st.secrets["PG_PASSWORD"],
                port=st.secrets["PG_PORT"]
            )

            cur = conn.cursor()

            status_text.success("Connected to Database")
            time.sleep(0.2)

        except Exception as e:

            st.error(f"Error connecting to Database: {e}")
            st.stop()

        # =========================
        # CREATE ONLY DSO COLUMN
        # =========================

        try:

            status_text.info("Creating DSO column if not exists...")
            time.sleep(0.2)

            query = f'''
            ALTER TABLE "DSO_SCORE"
            ADD COLUMN IF NOT EXISTS "{new_col}" NUMERIC;
            '''

            cur.execute(query)

            conn.commit()

            status_text.success("Column Ready")
            time.sleep(7)

        except Exception as e:

            st.error(f"Error creating column: {e}")

            cur.close()
            conn.close()

            st.stop()

        # =========================
        # PREPARE UPLOAD
        # =========================

        try:

            status_text.info("Preparing upload records...")
            time.sleep(0.2)

            records = sql_df[
                sql_df[new_col].notna()
            ][[
                "key",
                "Total Score",
                new_col
            ]].to_dict(orient="records")

        except Exception as e:

            st.error(f"Error preparing upload records: {e}")

            cur.close()
            conn.close()

            st.stop()

        # =========================
        # UPLOAD
        # =========================

        try:

            status_text.info("Uploading data...")
            time.sleep(0.2)

            batch_size = 500

            progress_bar = st.progress(0)

            total_batches = max(
                1,
                len(range(0, len(records), batch_size))
            )

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

            status_text.success("Upload Complete")
            time.sleep(0.2)

        except Exception as e:

            st.error(f"Error during upload: {e}")

            cur.close()
            conn.close()

            st.stop()

        # =========================
        # CLOSE CONNECTION
        # =========================

        try:

            status_text.info("Closing database connection...")
            time.sleep(0.2)

            cur.close()

            conn.close()

            status_text.success("Connection Closed")
            time.sleep(0.2)

        except Exception as e:

            st.error(f"Error closing connection: {e}")
            st.stop()

        # =========================
        # FINAL REPORT
        # =========================

        try:

            status_text.info("Preparing final download file...")
            time.sleep(0.2)

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

            # =========================
            # CREATE DYNAMIC BUCKETS
            # =========================

            dso_cols = sorted([
                col for col in download_df.columns
                if col.startswith("DSO_")
            ])

            for dso_col in dso_cols:

                suffix = dso_col.replace("DSO_", "")

                bucket_col = f"Bucket_{suffix}"

                download_df[bucket_col] = (
                    download_df[dso_col]
                    .apply(create_bucket)
                )

            # =========================
            # CREATE IMPACT + RANGE
            # =========================

            baseline_bucket_col = "Bucket_12_2025"

            for dso_col in dso_cols:
            
                if dso_col == "DSO_12_2025":
                    continue
            
                suffix = dso_col.replace("DSO_", "")
            
                current_bucket_col = f"Bucket_{suffix}"
            
                impact_col = f"Impact_{suffix}"
                range_col = f"Range_{suffix}"
            
                download_df[impact_col] = download_df.apply(
                    lambda row: calculate_impact(
                        row[baseline_bucket_col],
                        row[current_bucket_col]
                    ),
                    axis=1
                )
            
                download_df[range_col] = download_df.apply(
                    lambda row: calculate_range(
                        row[baseline_bucket_col],
                        row[dso_col]
                    ),
                    axis=1
                )

            # =========================
            # COLUMN ORDERING
            # =========================

            ordered_cols = []

            base_cols = [
                col for col in [
                    "HUB",
                    "key",
                    "Customer Code",
                    "Cluster"
                ]
                if col in download_df.columns
            ]

            ordered_cols.extend(base_cols)

            for i, dso_col in enumerate(dso_cols):

                suffix = dso_col.replace("DSO_", "")

                bucket_col = f"Bucket_{suffix}"

                ordered_cols.append(dso_col)
                ordered_cols.append(bucket_col)

                if i > 0:

                    impact_col = f"Impact_{suffix}"
                    range_col = f"Range_{suffix}"

                    if impact_col in download_df.columns:
                        ordered_cols.append(impact_col)

                    if range_col in download_df.columns:
                        ordered_cols.append(range_col)

            remaining_cols = [
                col for col in download_df.columns
                if col not in ordered_cols
                and col != "Total Score"
            ]

            ordered_cols.extend(remaining_cols)

            if "Total Score" in download_df.columns:
                ordered_cols.append("Total Score")

            download_df = download_df[ordered_cols]

            if "Total Score" in download_df.columns:

                download_df = download_df.sort_values(
                    by="Total Score",
                    ascending=False
                )

            csv_output = (
                download_df
                .to_csv(index=False)
                .encode("utf-8")
            )

            status_text.success("Final Report Ready")

            st.download_button(
                label="Download Report",
                data=csv_output,
                file_name="dso_score_output.csv",
                mime="text/csv"
            )

        except Exception as e:

            st.error(f"Error preparing final report: {e}")
            st.stop()


# =========================
# EXPANDERS
# =========================

with st.expander("What This Tool Does"):

    st.markdown("""
    - Uploads latest customer DSO data
    - Dynamically creates DSO buckets
    - Calculates customer movement impact
    - Calculates movement range
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

    ### Range Logic

    Based on:
    - Previous bucket
    - Current DSO

    ### Total Score Formula

    Total Score = Existing Total Score + Impact Score
    """)
