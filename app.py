import streamlit as st
import pandas as pd
import zipfile
import io

st.set_page_config(page_title="ETA/ATA Consistency Analysis", layout="centered")
st.title("ETA/ATA Consistency Analysis (Arauco)")

st.markdown(
    """
Upload your **shipment CSV** and then map the corresponding column names:

- **Identifier** (container or row identifier)
- **Shipment type** (must contain the value `"Container"` for container rows)
- **BOL ID**
- **AJ**: Destination ETA
- **AK**: Destination ATA

The app will:
- Filter rows where `shipment_type = "Container"`.
- Group by **BOL ID**.
- Check **AJ** and **AK** consistency across containers.
- Generate 6 CSV files and package them into a **ZIP**.
"""
)

uploaded_file = st.file_uploader("Upload shipment CSV", type=["csv"])


def n_unique(series: pd.Series) -> int:
    """Count distinct values, treating blanks as legitimate values."""
    return series.astype(str).nunique(dropna=False)


if uploaded_file is not None:
    try:
        # Read as string, normalize blanks
        df = pd.read_csv(uploaded_file, dtype=str)
        df = df.fillna("")

        st.write(f"Detected **{df.shape[0]} rows** and **{df.shape[1]} columns**.")

        # Let the user map columns by NAME
        st.subheader("Map CSV Columns")

        cols = list(df.columns)

        identifier_col = st.selectbox("Identifier column", options=cols)
        shipment_type_col = st.selectbox("Shipment type column", options=cols)
        bol_id_col = st.selectbox("BOL ID column", options=cols)
        aj_col = st.selectbox("AJ (ETA Destino) column", options=cols)
        ak_col = st.selectbox("AK (ATA Destino) column", options=cols)

        if st.button("Run ETA/ATA Analysis and Generate ZIP"):
            # Create normalized working columns
            work_df = df.copy()
            work_df["identifier"] = work_df[identifier_col].astype(str)
            work_df["shipment_type"] = work_df[shipment_type_col].astype(str)
            work_df["bol_id"] = work_df[bol_id_col].astype(str)
            work_df["aj"] = work_df[aj_col].astype(str)
            work_df["ak"] = work_df[ak_col].astype(str)

            # Filter containers
            containers = work_df[work_df["shipment_type"] == "Container"].copy()

            if containers.empty:
                st.warning(
                    "No rows found with shipment_type = 'Container' "
                    f"in column '{shipment_type_col}'."
                )
            else:
                st.info(
                    f"{len(containers)} rows where {shipment_type_col} = 'Container'."
                )

                # === UNIQUE BOLS ===
                unique_bols = (
                    containers[["bol_id"]]
                    .drop_duplicates()
                    .reset_index(drop=True)
                )

                # === GROUP & CLASSIFY BOLs ===
                grouped = containers.groupby("bol_id", dropna=False)

                bol_stats = grouped.agg(
                    n_aj=("aj", n_unique),
                    n_ak=("ak", n_unique),
                    row_count=("aj", "size"),
                ).reset_index()

                bols_same_aj = bol_stats[bol_stats["n_aj"] == 1]["bol_id"]
                bols_diff_aj = bol_stats[bol_stats["n_aj"] > 1]["bol_id"]

                bols_same_ak = bol_stats[bol_stats["n_ak"] == 1]["bol_id"]
                bols_diff_ak = bol_stats[bol_stats["n_ak"] > 1]["bol_id"]

                base_cols = ["bol_id", "identifier", "shipment_type", "aj", "ak"]

                same_aj_df = containers[
                    containers["bol_id"].isin(bols_same_aj)
                ][base_cols].copy()

                different_aj_df = containers[
                    containers["bol_id"].isin(bols_diff_aj)
                ][base_cols].copy()

                same_ak_df = containers[
                    containers["bol_id"].isin(bols_same_ak)
                ][base_cols].copy()

                different_ak_df = containers[
                    containers["bol_id"].isin(bols_diff_ak)
                ][base_cols].copy()

                # === SUMMARY ===
                summary_rows = [
                    {
                        "case": "total_container_rows",
                        "description": "Total rows with shipment_type = 'Container'",
                        "count": len(containers),
                    },
                    {
                        "case": "unique_bols",
                        "description": "Distinct BOL IDs among Container rows (including blanks)",
                        "count": unique_bols["bol_id"].nunique(dropna=False),
                    },
                    {
                        "case": "bols_same_aj",
                        "description": "BOLs where containers share exactly 1 unique AJ (including single-container BOLs)",
                        "count": len(bols_same_aj),
                    },
                    {
                        "case": "bols_different_aj",
                        "description": "BOLs where containers have more than 1 unique AJ (blanks treated as distinct)",
                        "count": len(bols_diff_aj),
                    },
                    {
                        "case": "bols_same_ak",
                        "description": "BOLs where containers share exactly 1 unique AK (including single-container BOLs)",
                        "count": len(bols_same_ak),
                    },
                    {
                        "case": "bols_different_ak",
                        "description": "BOLs where containers have more than 1 unique AK (blanks treated as distinct)",
                        "count": len(bols_diff_ak),
                    },
                ]

                summary_df = pd.DataFrame(
                    summary_rows, columns=["case", "description", "count"]
                )

                # === BUILD ZIP IN MEMORY ===
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(
                        "unique_bols.csv",
                        unique_bols.to_csv(index=False).encode("utf-8"),
                    )
                    zf.writestr(
                        "different_aj.csv",
                        different_aj_df.to_csv(index=False).encode("utf-8"),
                    )
                    zf.writestr(
                        "different_ak.csv",
                        different_ak_df.to_csv(index=False).encode("utf-8"),
                    )
                    zf.writestr(
                        "same_aj.csv",
                        same_aj_df.to_csv(index=False).encode("utf-8"),
                    )
                    zf.writestr(
                        "same_ak.csv",
                        same_ak_df.to_csv(index=False).encode("utf-8"),
                    )
                    zf.writestr(
                        "summary.csv",
                        summary_df.to_csv(index=False).encode("utf-8"),
                    )

                zip_buffer.seek(0)

                st.success("Analysis completed. Download the ZIP below.")
                st.download_button(
                    label="Download ETA/ATA Analysis ZIP",
                    data=zip_buffer,
                    file_name="eta_ata_analysis.zip",
                    mime="application/zip",
                )

                st.subheader("Summary (preview)")
                st.dataframe(summary_df)

    except Exception as e:
        st.error(f"Error processing file: {e}")

else:
    st.info("Upload a CSV file to begin.")
