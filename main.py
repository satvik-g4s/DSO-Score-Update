import streamlit as st
import pandas as pd
import numpy as np
import psycopg2
import time
from supabase import create_client

st.set_page_config(layout="wide")

st.title("DSO Score Management System")

# =========================
# CONNECTIONS
# =========================

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

supabase = create_client(url, key)

conn = psycopg2.connect(
    host=st.secrets["PG_HOST"],
    database=st.secrets["PG_DATABASE"],
    user=st.secrets["PG_USER"],
    password=st.secrets["PG_PASSWORD"],
    port=st.secrets["PG_PORT"]
)

cur = conn.cursor()

# =========================
# SESSION STATE
# =========================

if "base_column" not in st.session_state:
    st.session_state.base_column = "DSO_12_2025"

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
# FETCH MASTER DATA
# =========================

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

master_df = pd.DataFrame(all_rows)

dso_columns = sorted([
    col for col in master_df.columns
    if col.startswith("DSO_")
])

# =========================
# TABS
# =========================

tab1, tab2, tab3 = st.tabs([
    "Download Report",
    "Upload Data",
    "Admin Controls"
])

# =========================================================
# TAB 1 - DOWNLOAD REPORT
# =========================================================

with tab1:

    st.subheader("Download Final Report")

    if st.button("Generate Report"):

        try:

            status = st.empty()

            status.info("Preparing report...")

            download_df = master_df.copy()

            # =========================
            # CREATE BUCKETS
            # =========================

            for dso_col in dso_columns:

                suffix = dso_col.replace("DSO_", "")

                bucket_col = f"Bucket_{suffix}"

                download_df[bucket_col] = (
                    download_df[dso_col]
                    .apply(create_bucket)
                )

            # =========================
            # CREATE IMPACT + RANGE
            # =========================

            baseline_bucket_col = (
                f'Bucket_{st.session_state.base_column.replace("DSO_", "")}'
            )

            for dso_col in dso_columns:

                if dso_col == st.session_state.base_column:
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

            for i, dso_col in enumerate(dso_columns):

                suffix = dso_col.replace("DSO_", "")

                bucket_col = f"Bucket_{suffix}"

                ordered_cols.append(dso_col)
                ordered_cols.append(bucket_col)

                if dso_col != st.session_state.base_column:

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

            status.success("Report Ready")

            st.download_button(
                label="Download Report",
                data=csv_output,
                file_name="dso_score_output.csv",
                mime="text/csv"
            )

        except Exception as e:

            st.error(f"Error preparing report: {e}")

# =========================================================
# TAB 2 - UPLOAD DATA
# =========================================================

with tab2:

    st.subheader("Upload New DSO Data")

    uploaded_file = st.file_uploader(
        "Upload CSV File",
        type=["csv"]
    )

    st.caption("Required Columns: Cluster, Customer Code, DSO")

    selected_month = st.text_input(
        "Select Reporting Month",
        value="03/2026",
        placeholder="MM/YYYY"
    )

    run = st.button("Run Upload")

    log_container = st.container()

    if run:

        with log_container:

            status_text = st.empty()

            if uploaded_file is None:
                st.error("Please upload the CSV file.")
                st.stop()

            try:

                parsed_date = pd.to_datetime(
                    selected_month,
                    format="%m/%Y"
                )

                monthh = parsed_date.month
                yearr = parsed_date.year

                new_col = f"DSO_{monthh}_{yearr}"
                impact_col = f"Impact_{monthh}_{yearr}"

            except:

                st.error("Enter month in MM/YYYY format.")
                st.stop()

            # =========================
            # FETCH DATABASE
            # =========================

            try:

                status_text.info(
                    "Fetching existing records from Database..."
                )

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

                st.error(f"Error fetching data: {e}")
                st.stop()

            # =========================
            # READ CSV
            # =========================

            try:

                status_text.info("Reading uploaded CSV file...")
                time.sleep(0.2)

                DSO = pd.read_csv(uploaded_file)

            except Exception as e:

                st.error(f"Error reading CSV: {e}")
                st.stop()

            # =========================
            # VALIDATE COLUMNS
            # =========================

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

            # =========================
            # CLEAN INPUT
            # =========================

            try:

                status_text.info("Preparing data...")
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

                st.error(f"Error preprocessing: {e}")
                st.stop()

            # =========================
            # BASE COLUMN
            # =========================

            previous_dso_col = st.session_state.base_column

            # =========================
            # MERGE
            # =========================

            sql_df = pd.merge(
                sql_df,
                DSO,
                on="key",
                how="left"
            )

            # =========================
            # TEMP BUCKETS
            # =========================

            temp_old_bucket = "temp_old_bucket"
            temp_new_bucket = "temp_new_bucket"

            sql_df[temp_new_bucket] = (
                sql_df[new_col]
                .apply(create_bucket)
            )

            sql_df[temp_old_bucket] = (
                sql_df[previous_dso_col]
                .apply(create_bucket)
            )

            sql_df[impact_col] = sql_df.apply(
                lambda row: calculate_impact(
                    row[temp_old_bucket],
                    row[temp_new_bucket]
                ),
                axis=1
            )

            # =========================
            # UPDATE SCORE
            # =========================

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

            sql_df[new_col] = (
                pd.to_numeric(
                    sql_df[new_col],
                    errors="coerce"
                )
            )

            sql_df = sql_df.replace({np.nan: None})

            # =========================
            # CREATE COLUMN
            # =========================

            try:

                status_text.info("Creating DSO column...")
                time.sleep(0.2)

                query = f'''
                ALTER TABLE "DSO_SCORE"
                ADD COLUMN IF NOT EXISTS "{new_col}" NUMERIC;
                '''

                cur.execute(query)

                conn.commit()

                status_text.success("Column Ready")

            except Exception as e:

                st.error(f"Error creating column: {e}")
                st.stop()

            # =========================
            # PREPARE RECORDS
            # =========================

            records = sql_df[
                sql_df[new_col].notna()
            ][[
                "key",
                "Total Score",
                new_col
            ]].to_dict(orient="records")

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

            except Exception as e:

                st.error(f"Error during upload: {e}")

# =========================================================
# TAB 3 - ADMIN CONTROLS
# =========================================================

with tab3:

    st.subheader("Admin Controls")

    st.warning(
        "These operations permanently modify the database."
    )

    # =========================
    # BASE COLUMN
    # =========================

    selected_base = st.selectbox(
        "Select Base DSO Column",
        dso_columns,
        index=dso_columns.index(
            st.session_state.base_column
        )
    )

    if selected_base != st.session_state.base_column:

        st.error(
            f"""
            WARNING:

            Changing base column will affect:
            - Impact calculations
            - Range calculations
            - Future uploads
            """
        )

        confirm_base = st.checkbox(
            f"Confirm changing base column to {selected_base}"
        )

        if confirm_base:

            if st.button("Update Base Column"):

                st.session_state.base_column = selected_base

                st.success(
                    f"Base column updated to {selected_base}"
                )

                st.rerun()

    # =========================
    # DELETE DSO COLUMN
    # =========================

    st.divider()

    deletable_columns = [
        col for col in dso_columns
        if col != st.session_state.base_column
    ]

    delete_col = st.selectbox(
        "Delete DSO Column",
        ["Select Column"] + deletable_columns
    )

    if delete_col != "Select Column":

        st.error(
            f"""
            WARNING:

            This will permanently delete:
            - {delete_col}

            This action cannot be undone.
            """
        )

        confirm_delete = st.checkbox(
            f"Confirm deletion of {delete_col}"
        )

        if confirm_delete:

            if st.button("Delete Column"):

                try:

                    query = f'''
                    ALTER TABLE "DSO_SCORE"
                    DROP COLUMN IF EXISTS "{delete_col}";
                    '''

                    cur.execute(query)

                    conn.commit()

                    st.success(
                        f"{delete_col} deleted successfully."
                    )

                    st.rerun()

                except Exception as e:

                    st.error(f"Error: {e}")

    # =========================
    # RESET TOTAL SCORE
    # =========================

    st.divider()

    st.error(
        """
        WARNING:

        This will reset ALL Total Scores to 100.
        """
    )

    confirm_reset = st.checkbox(
        "Confirm Total Score Reset"
    )

    if confirm_reset:

        if st.button("Reset Total Score"):

            try:

                query = '''
                UPDATE "DSO_SCORE"
                SET "Total Score" = 100;
                '''

                cur.execute(query)
                conn.commit()

                st.success(
                    "Total Score reset completed."
                )

            except Exception as e:

                st.error(f"Error: {e}")

# =========================
# CLOSE CONNECTIONS
# =========================

cur.close()
conn.close()
