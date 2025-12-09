"""
Global Lab Tests Page - Clean Table View.

Displays all standardized extracted data from each file in a clean table format.
"""

import os
import streamlit as st
import requests
import pandas as pd

# API URL
API_URL = os.environ.get("API_URL", "http://localhost:6000/api/v1")

st.set_page_config(
    page_title="Global Lab Tests",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Global Lab Results Table")
st.caption("All standardized extracted data from uploaded lab reports")

# =============================================================================
# Quick Stats
# =============================================================================

try:
    stats_response = requests.get(f"{API_URL}/tests/stats", timeout=10)
    
    if stats_response.status_code == 200:
        stats = stats_response.json()
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Tests", f"{stats.get('total_tests', 0):,}")
        col2.metric("Unique Patients", stats.get('unique_patients', 0))
        col3.metric("Test Types", stats.get('unique_test_types', 0))
        col4.metric("Standardization Rate", f"{stats.get('standardization_rate', 0):.1%}")
        
except requests.exceptions.ConnectionError:
    st.error(f"Cannot connect to backend at {API_URL}")
    st.stop()
except Exception as e:
    st.warning(f"Could not load statistics: {e}")

st.divider()

# =============================================================================
# Filters
# =============================================================================

st.subheader("🔍 Filters")

filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    file_search = st.text_input("Search by Filename", "", placeholder="Enter filename...")

with filter_col2:
    patient_search = st.text_input("Search by Patient Name", "", placeholder="Enter patient name...")

with filter_col3:
    # Category filter
    categories = []
    try:
        cat_response = requests.get(f"{API_URL}/tests/categories", timeout=5)
        if cat_response.status_code == 200:
            cat_data = cat_response.json()
            categories = [c['name'] for c in cat_data.get('categories', [])]
    except:
        pass
    
    selected_category = st.selectbox(
        "Filter by Category",
        options=["All Categories"] + categories,
        index=0
    )

st.divider()

# =============================================================================
# Main Data Table
# =============================================================================

st.subheader("📋 Extracted Lab Results")

try:
    params = {"limit": 2000}
    if selected_category != "All Categories":
        params['category'] = selected_category
    if patient_search:
        params['patient_name'] = patient_search
    if file_search:
        params['source_file'] = file_search
    
    tests_response = requests.get(f"{API_URL}/tests/all", params=params, timeout=30)
    
    if tests_response.status_code == 200:
        tests_data = tests_response.json()
        tests = tests_data.get('tests', [])
        
        if tests:
            st.caption(f"Showing {len(tests)} extracted test results")
            
            df = pd.DataFrame(tests)
            
            # Define display columns in order
            display_columns = [
                'source_filename',
                'patient_name',
                'patient_id',
                'standardized_test_name',
                'original_test_name',
                'value',
                'unit',
                'reference_range',
                'flag',
                'category'
            ]
            
            # Only use columns that exist
            display_columns = [c for c in display_columns if c in df.columns]
            df_display = df[display_columns].copy()
            
            # Rename for display
            column_names = {
                'source_filename': 'Source File',
                'patient_name': 'Patient Name',
                'patient_id': 'Patient ID',
                'standardized_test_name': 'Test Name (Standardized)',
                'original_test_name': 'Original Name',
                'value': 'Value',
                'unit': 'Unit',
                'reference_range': 'Reference Range',
                'flag': 'Flag',
                'category': 'Category'
            }
            df_display = df_display.rename(columns=column_names)
            
            # Fill NaN values
            df_display = df_display.fillna('')
            
            # Display table
            st.dataframe(
                df_display,
                use_container_width=True,
                height=600,
                hide_index=True
            )
            
            # =============================================================================
            # Export Options
            # =============================================================================
            
            st.divider()
            st.subheader("📥 Export Data")
            
            export_col1, export_col2 = st.columns(2)
            
            with export_col1:
                csv = df_display.to_csv(index=False)
                st.download_button(
                    label="📄 Download as CSV",
                    data=csv,
                    file_name="lab_results_all.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with export_col2:
                # Group by file for summary
                if 'Source File' in df_display.columns:
                    files = df_display['Source File'].nunique()
                    st.info(f"📁 Data from {files} unique files")
            
            # =============================================================================
            # Summary by File
            # =============================================================================
            
            with st.expander("📁 Summary by Source File", expanded=False):
                if 'source_filename' in df.columns:
                    file_summary = df.groupby('source_filename').agg({
                        'standardized_test_name': 'count',
                        'patient_name': 'first',
                        'patient_id': 'first'
                    }).reset_index()
                    
                    file_summary.columns = ['Filename', 'Test Count', 'Patient Name', 'Patient ID']
                    file_summary = file_summary.fillna('')
                    
                    st.dataframe(file_summary, use_container_width=True, hide_index=True)
        else:
            st.info("No test data available. Upload and process some lab reports first!")
            
            st.markdown("""
            ### How to get started:
            1. Go to the **Home** page
            2. Upload lab report images (PNG, JPG, PDF)
            3. Wait for processing to complete
            4. Come back here to see all extracted results
            """)
            
    else:
        st.error(f"Failed to load tests: {tests_response.text}")
        
except Exception as e:
    st.error(f"Error loading tests: {e}")

# =============================================================================
# Footer
# =============================================================================

st.divider()
st.caption("Data is sorted by source filename, then by test name")
