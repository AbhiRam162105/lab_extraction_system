"""
Global Lab Tests Page.

Displays all lab test results across all patients in a pivot table format
with filtering, export, and analytics capabilities.
"""

import os
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# API URL
API_URL = os.environ.get("API_URL", "http://localhost:6000/api/v1")

st.set_page_config(
    page_title="Global Lab Tests",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Global Lab Tests Dashboard")
st.caption("Aggregated view of all lab tests across all patients")

# =============================================================================
# Statistics Section
# =============================================================================

st.header("📈 Analytics Overview")

try:
    stats_response = requests.get(f"{API_URL}/tests/stats", timeout=10)
    
    if stats_response.status_code == 200:
        stats = stats_response.json()
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Tests", f"{stats.get('total_tests', 0):,}")
        col2.metric("Unique Patients", stats.get('unique_patients', 0))
        col3.metric("Test Types", stats.get('unique_test_types', 0))
        col4.metric(
            "Standardization Rate", 
            f"{stats.get('standardization_rate', 0):.1%}"
        )
        
        # Match type distribution chart
        match_dist = stats.get('match_type_distribution', {})
        if match_dist:
            with st.expander("📊 Match Type Distribution", expanded=False):
                fig = px.pie(
                    names=list(match_dist.keys()),
                    values=list(match_dist.values()),
                    title="How tests were standardized",
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                st.plotly_chart(fig, width="stretch")
    else:
        st.info("No test statistics available yet. Upload some lab reports first!")
        
except requests.exceptions.ConnectionError:
    st.error(f"Cannot connect to backend at {API_URL}")
    st.stop()
except Exception as e:
    st.warning(f"Could not load statistics: {e}")

st.divider()

# =============================================================================
# Filters Section
# =============================================================================

st.header("🔍 Filters")

filter_col1, filter_col2, filter_col3 = st.columns(3)

# Category filter
categories = []
try:
    cat_response = requests.get(f"{API_URL}/tests/categories", timeout=5)
    if cat_response.status_code == 200:
        cat_data = cat_response.json()
        categories = [c['name'] for c in cat_data.get('categories', [])]
except:
    pass

with filter_col1:
    selected_category = st.selectbox(
        "Category",
        options=["All Categories"] + categories,
        index=0
    )

with filter_col2:
    patient_search = st.text_input("Search Patient Name", "")

with filter_col3:
    view_mode = st.radio(
        "View Mode",
        options=["Pivot Table", "Flat List"],
        horizontal=True
    )

st.divider()

# =============================================================================
# Main Data Display
# =============================================================================

if view_mode == "Pivot Table":
    st.header("📋 Patient × Tests Matrix")
    
    try:
        params = {}
        if selected_category != "All Categories":
            params['category'] = selected_category
        
        pivot_response = requests.get(f"{API_URL}/tests/pivot", params=params, timeout=30)
        
        if pivot_response.status_code == 200:
            pivot_data = pivot_response.json()
            
            if pivot_data.get('rows'):
                st.caption(
                    f"Showing {pivot_data.get('patient_count', 0)} patients × "
                    f"{pivot_data.get('test_count', 0)} unique tests"
                )
                
                # Convert to DataFrame
                df = pd.DataFrame(pivot_data['rows'])
                
                # Filter by patient name if specified
                if patient_search:
                    df = df[
                        df['patient'].str.contains(patient_search, case=False, na=False) |
                        df['patient_name'].str.contains(patient_search, case=False, na=False)
                    ]
                
                # Reorder columns: Patient info first, then tests
                display_cols = ['patient', 'patient_name', 'patient_id']
                test_cols = [c for c in df.columns if c not in ['patient', 'patient_name', 'patient_id']]
                
                # Only show existing columns
                display_cols = [c for c in display_cols if c in df.columns]
                df_display = df[display_cols + sorted(test_cols)]
                
                # Display with horizontal scroll
                st.dataframe(
                    df_display,
                    width="stretch",
                    height=500
                )
                
                # Download buttons
                st.subheader("📥 Export Data")
                export_col1, export_col2 = st.columns(2)
                
                with export_col1:
                    csv = df_display.to_csv(index=False)
                    st.download_button(
                        label="📄 Download CSV",
                        data=csv,
                        file_name="lab_tests_pivot.csv",
                        mime="text/csv"
                    )
                
                with export_col2:
                    # Excel export via API
                    if st.button("📊 Download Excel (Full Data)"):
                        export_params = {'format': 'excel'}
                        if selected_category != "All Categories":
                            export_params['category'] = selected_category
                        
                        st.info("Use the API endpoint: /api/v1/tests/export?format=excel")
            else:
                st.info("No test data available. Upload and process some lab reports first!")
                
        else:
            st.error(f"Failed to load pivot data: {pivot_response.text}")
            
    except Exception as e:
        st.error(f"Error loading pivot table: {e}")

else:
    st.header("📋 All Tests (Flat View)")
    
    try:
        params = {"limit": 500}
        if selected_category != "All Categories":
            params['category'] = selected_category
        if patient_search:
            params['patient_name'] = patient_search
        
        tests_response = requests.get(f"{API_URL}/tests/all", params=params, timeout=30)
        
        if tests_response.status_code == 200:
            tests_data = tests_response.json()
            tests = tests_data.get('tests', [])
            
            if tests:
                st.caption(f"Showing {len(tests)} tests")
                
                df = pd.DataFrame(tests)
                
                # Format columns
                display_columns = [
                    'patient_name',
                    'standardized_test_name',
                    'original_test_name',
                    'value',
                    'unit',
                    'reference_range',
                    'flag',
                    'category',
                    'loinc_code',
                    'match_type',
                    'confidence'
                ]
                
                # Only use columns that exist
                display_columns = [c for c in display_columns if c in df.columns]
                df_display = df[display_columns]
                
                # Rename for display
                df_display = df_display.rename(columns={
                    'patient_name': 'Patient',
                    'standardized_test_name': 'Standardized Name',
                    'original_test_name': 'Original Name',
                    'value': 'Value',
                    'unit': 'Unit',
                    'reference_range': 'Reference',
                    'flag': 'Flag',
                    'category': 'Category',
                    'loinc_code': 'LOINC',
                    'match_type': 'Match Type',
                    'confidence': 'Confidence'
                })
                
                # Color-code match types
                def highlight_match_type(val):
                    if val == 'exact':
                        return 'background-color: #90EE90'  # Light green
                    elif val == 'semantic':
                        return 'background-color: #87CEEB'  # Light blue
                    elif val == 'llm':
                        return 'background-color: #FFD700'  # Gold
                    elif val == 'fuzzy':
                        return 'background-color: #DDA0DD'  # Plum
                    else:
                        return 'background-color: #FFB6C1'  # Light pink
                
                st.dataframe(
                    df_display,
                    width="stretch",
                    height=500
                )
                
                # Download
                csv = df_display.to_csv(index=False)
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name="lab_tests_flat.csv",
                    mime="text/csv"
                )
            else:
                st.info("No test data available. Upload and process some lab reports first!")
                
        else:
            st.error(f"Failed to load tests: {tests_response.text}")
            
    except Exception as e:
        st.error(f"Error loading tests: {e}")

st.divider()

# =============================================================================
# Test Definitions Reference
# =============================================================================

with st.expander("📚 Standardized Test Definitions Reference"):
    try:
        defs_response = requests.get(f"{API_URL}/tests/definitions", timeout=10)
        
        if defs_response.status_code == 200:
            defs_data = defs_response.json()
            definitions = defs_data.get('definitions', [])
            
            if definitions:
                # Group by category
                by_category = {}
                for d in definitions:
                    cat = d.get('category', 'Other')
                    if cat not in by_category:
                        by_category[cat] = []
                    by_category[cat].append(d)
                
                for category, tests in sorted(by_category.items()):
                    st.subheader(f"🏷️ {category}")
                    
                    df = pd.DataFrame([
                        {
                            "Canonical Name": t['canonical_name'],
                            "LOINC": t['loinc_code'] or "-",
                            "Unit": t['unit'] or "-",
                            "Aliases": ", ".join(t['aliases'][:5]) + ("..." if len(t['aliases']) > 5 else "")
                        }
                        for t in tests
                    ])
                    
                    st.dataframe(df, width="stretch", hide_index=True)
            else:
                st.info("No test definitions loaded yet.")
                
    except Exception as e:
        st.warning(f"Could not load test definitions: {e}")
