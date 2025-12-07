import os
import streamlit as st
import requests
import pandas as pd
import json
import time


# API URL - use environment variable in Docker, fallback to localhost
API_URL = os.environ.get("API_URL", "http://localhost:6000/api/v1")


def flatten_json_to_list(data, parent_key=''):
    """
    Recursively searches for list-like or dict-like items that contain 'value' or 'result' 
    and flattens them into a single list of dictionaries for table display.
    """
    rows = []
    
    if isinstance(data, dict):
        # customized heuristics for the specific lab report structure shown by user
        # Check if this dict represents a single test result
        if any(k in data for k in ['result', 'value']):
            # It's a single result row
            row = data.copy()
            
            # Infer test_name from parent_key if missing
            if 'test_name' not in row and parent_key:
                # Clean up generic suffixes
                clean_name = parent_key
                for suffix in [' > values', ' > result', ' > results', 'values', 'result']:
                    if clean_name.endswith(suffix):
                        clean_name = clean_name[:-len(suffix)]
                    elif clean_name == suffix:
                        clean_name = "Unknown Test"
                
                if clean_name.strip():
                     row['test_name'] = clean_name.strip(" >")
            
            if parent_key:
                row['category'] = parent_key
            rows.append(row)
        else:
            # It's a container (like "hematology": {...})
            for key, value in data.items():
                new_key = f"{parent_key} > {key}" if parent_key else key
                rows.extend(flatten_json_to_list(value, new_key))
                
    elif isinstance(data, list):
        for item in data:
            rows.extend(flatten_json_to_list(item, parent_key))
            
    return rows


def format_standardization_badge(std_info):
    """Create a badge showing standardization status."""
    if not std_info or not std_info.get('is_standardized'):
        return "⚠️ Not Standardized"
    
    confidence = std_info.get('confidence', 0)
    match_type = std_info.get('match_type', 'unknown')
    
    if confidence >= 0.95:
        return f"✅ {match_type.title()} Match"
    elif confidence >= 0.85:
        return f"🔶 {match_type.title()} ({confidence:.0%})"
    else:
        return f"🔸 {match_type.title()} ({confidence:.0%})"


st.set_page_config(
    page_title="Lab Extraction",
    page_icon="🧬",
    layout="wide"
)

st.title("🧬 Enterprise Lab Report Extraction")
st.caption("With AI-powered test name standardization and LOINC codes")

tab1, tab2 = st.tabs(["Upload", "Dashboard"])

with tab1:
    st.header("Upload Documents")
    uploaded_files = st.file_uploader(
        "Choose PDF or Image files", 
        accept_multiple_files=True
    )
    
    if st.button("Process Files") and uploaded_files:
        files = []
        for file in uploaded_files:
            files.append(('files', (file.name, file.getvalue(), file.type)))
            
        with st.spinner("Uploading and queueing..."):
            try:
                response = requests.post(f"{API_URL}/upload", files=files)
                if response.status_code == 200:
                    st.success(f"Successfully uploaded {len(uploaded_files)} files!")
                    st.json(response.json())
                else:
                    st.error(f"Upload failed: {response.text}")
            except Exception as e:
                st.error(f"Connection error: {e}")

with tab2:
    st.header("Extraction Dashboard")
    
    if st.button("Refresh Data"):
        st.rerun()
        
    try:
        response = requests.get(f"{API_URL}/documents")
        if response.status_code == 200:
            doc_data = response.json()
            if doc_data:
                df = pd.DataFrame(doc_data)
                
                # Metrics
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Documents", len(df))
                col2.metric("Completed", len(df[df['status'] == 'completed']))
                col3.metric("Processing", len(df[df['status'] == 'processing']))
                col4.metric("Failed", len(df[df['status'] == 'failed']))
                
                # Main Table
                st.dataframe(df, use_container_width=True)
                
                # Detail View
                selected_id = st.selectbox("Select Document ID for Details", df['id'].tolist())
                if selected_id:
                    res_response = requests.get(f"{API_URL}/results/{selected_id}")
                    if res_response.status_code == 200:
                        detail_data = res_response.json()
                        st.subheader("Extraction Analysis")
                        
                        col_img, col_json = st.columns(2)
                        
                        with col_img:
                            st.markdown("### Original Document")
                            if detail_data.get("document", {}).get("file_path"):
                                file_path = detail_data["document"]["file_path"]
                                
                                if os.path.exists(file_path):
                                    st.image(file_path, caption=os.path.basename(file_path), use_container_width=True)
                                else:
                                    st.error(f"File not found on server: {file_path}")
                            else:
                                st.warning("Image not found")

                        with col_json:
                            st.markdown("### Extracted Data")
                            extraction = detail_data.get("extraction")
                            if extraction:
                                data = extraction.get("extracted_data", {})
                                
                                # Display extraction metadata
                                metadata = data.get("metadata", {})
                                if metadata:
                                    with st.expander("📊 Extraction Metadata", expanded=True):
                                        meta_col1, meta_col2 = st.columns(2)
                                        
                                        with meta_col1:
                                            confidence = metadata.get("confidence_score", 0)
                                            st.metric("Confidence", f"{confidence:.1%}")
                                            
                                            std_info = metadata.get("standardization", {})
                                            if std_info:
                                                rate = std_info.get("standardization_rate", 0)
                                                st.metric("Standardization Rate", f"{rate:.0%}")
                                        
                                        with meta_col2:
                                            total_tests = metadata.get("total_tests_extracted", 
                                                         len(data.get("lab_results", [])))
                                            st.metric("Tests Extracted", total_tests)
                                            
                                            if metadata.get("needs_review"):
                                                st.error("⚠️ Needs Review")
                                
                                # Try standard schema first
                                if "lab_results" in data and isinstance(data["lab_results"], list):
                                    st.subheader("Lab Results Table")
                                    results = data["lab_results"]
                                    
                                    # Create enhanced dataframe
                                    display_data = []
                                    for result in results:
                                        row = {
                                            "Test Name": result.get("test_name", ""),
                                            "Original Name": result.get("original_name", result.get("test_name", "")),
                                            "Value": result.get("value", ""),
                                            "Unit": result.get("unit", ""),
                                            "Reference Range": result.get("reference_range", ""),
                                            "Category": result.get("category", ""),
                                            "LOINC": result.get("loinc_code", ""),
                                        }
                                        
                                        # Add standardization info
                                        std = result.get("standardization", {})
                                        if std:
                                            row["Std. Match"] = format_standardization_badge(std)
                                        
                                        display_data.append(row)
                                    
                                    results_df = pd.DataFrame(display_data)
                                    
                                    # Highlight LOINC codes
                                    st.dataframe(results_df, use_container_width=True)
                                    
                                    # Patient Info
                                    if "patient_info" in data:
                                        st.subheader("Patient Info")
                                        patient = data["patient_info"]
                                        if patient:
                                            patient_df = pd.DataFrame([patient])
                                            st.dataframe(patient_df, use_container_width=True)

                                    # Review Alert
                                    if detail_data.get("extraction", {}).get("needs_review"):
                                        st.error("⚠️ Flagged for Review")
                                        reason = detail_data.get("extraction", {}).get("review_reason")
                                        if reason:
                                            st.write(f"**Reason:** {reason}")

                                else:
                                    # Try heuristics to flatten arbitrary JSON
                                    flattened_rows = flatten_json_to_list(data)
                                    if flattened_rows:
                                        st.subheader("Lab Results Table (Flattened)")
                                        flat_df = pd.DataFrame(flattened_rows)
                                        
                                        # Reorder columns to put interesting ones first if they exist
                                        cols = flat_df.columns.tolist()
                                        priority_cols = ['test_name', 'result', 'value', 'unit', 'units', 'reference_range', 'loinc_code']
                                        sorted_cols = [c for c in priority_cols if c in cols] + [c for c in cols if c not in priority_cols]
                                        
                                        st.dataframe(flat_df[sorted_cols], use_container_width=True)
                                        # Also show raw JSON for checking
                                        with st.expander("View Raw JSON"):
                                            st.json(data)
                                    else:
                                        # Fallback
                                        st.json(data)
                            else:
                                st.info("No extraction data available yet.")
            else:
                st.info("No documents found.")
        else:
            st.error("Failed to fetch documents")
            
    except Exception as e:
        st.error(f"Connection error: {e}")
        st.warning(f"Ensure backend is running on {API_URL.replace('/api/v1', '')}")
