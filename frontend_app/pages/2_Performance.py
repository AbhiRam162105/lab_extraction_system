"""
Performance Monitoring Page

Displays system performance metrics including:
- Document processing stats
- Test extraction statistics  
- Processing timing (7-step pipeline)
"""

import streamlit as st
import requests
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# API configuration
API_URL = os.environ.get("API_URL", "http://localhost:6000/api/v1")

st.set_page_config(
    page_title="Performance Monitor",
    page_icon="📊",
    layout="wide"
)

st.title("📊 System Performance Monitor")
st.markdown("Real-time monitoring of the 7-step extraction pipeline.")

# Auto-refresh toggle
col_refresh, col_interval = st.columns([1, 3])
with col_refresh:
    auto_refresh = st.toggle("Auto-refresh", value=False)
with col_interval:
    refresh_interval = st.slider("Refresh interval (seconds)", 5, 60, 10)

if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()

# Manual refresh button
if st.button("🔄 Refresh Now"):
    st.rerun()

st.divider()

# =============================================================================
# Pipeline Overview
# =============================================================================
st.subheader("🔄 Extraction Pipeline (7 Steps)")

pipeline_steps = """
| Step | Name | Description |
|------|------|-------------|
| 1 | **Image Quality** | Evaluate image quality, preprocessing |
| 2 | **Vision Extraction** | Gemini Vision API call (extract raw data) |
| 3 | **Normalization** | Deterministic test name standardization |
| 4 | **LLM Validation** | Second Gemini call for sanity check |
| 5 | **Panel Validation** | Check for missing expected tests |
| 6 | **Patient Memory** | Match/generate patient ID |
| 7 | **Summary** | Generate extraction summary |
"""
st.markdown(pipeline_steps)

st.divider()

# =============================================================================
# Document Processing Stats
# =============================================================================
col1, col2 = st.columns(2)

with col1:
    st.subheader("📄 Document Processing")
    try:
        response = requests.get(f"{API_URL}/documents", timeout=5)
        if response.status_code == 200:
            documents = response.json()
            
            # Count by status
            status_counts = {"completed": 0, "failed": 0, "processing": 0, "pending": 0}
            for doc in documents:
                status = doc.get("status", "pending")
                if status in status_counts:
                    status_counts[status] += 1
            
            # Metrics
            st.metric("Total Documents", len(documents))
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("✅ Completed", status_counts["completed"])
            with col_b:
                st.metric("❌ Failed", status_counts["failed"])
            
            col_c, col_d = st.columns(2)
            with col_c:
                st.metric("⏳ Processing", status_counts["processing"])
            with col_d:
                st.metric("📋 Pending", status_counts["pending"])
            
            # Success rate
            completed = status_counts["completed"]
            failed = status_counts["failed"]
            if completed + failed > 0:
                success_rate = completed / (completed + failed) * 100
                st.progress(success_rate / 100, text=f"Success Rate: {success_rate:.0f}%")
        else:
            st.error(f"Error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        st.error(f"Connection error: {str(e)[:50]}")

# =============================================================================
# Test Statistics
# =============================================================================
with col2:
    st.subheader("🧪 Test Extraction Statistics")
    try:
        response = requests.get(f"{API_URL}/tests/stats", timeout=5)
        if response.status_code == 200:
            test_stats = response.json()
            
            st.metric("Total Tests Extracted", test_stats.get("total_tests", 0))
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Unique Patients", test_stats.get("unique_patients", 0))
            with col_b:
                st.metric("Unique Test Types", test_stats.get("unique_test_types", 0))
            
            rate = test_stats.get("standardization_rate", 0) * 100
            st.progress(rate / 100, text=f"Standardization Rate: {rate:.1f}%")
            
    except requests.exceptions.RequestException as e:
        st.error(f"Connection error: {str(e)[:50]}")

st.divider()

# =============================================================================
# Processing Timing - 7 Step Pipeline
# =============================================================================
st.subheader("⏱️ Processing Timing (7-Step Pipeline)")

try:
    response = requests.get(f"{API_URL}/tests/timing-stats", timeout=5)
    if response.status_code == 200:
        timing_stats = response.json()
        
        total_processed = timing_stats.get("total_processed", 0)
        
        if total_processed > 0:
            # Average timing metrics - 7 columns for 7 steps
            col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
            
            with col1:
                avg_preprocess = timing_stats.get("avg_preprocessing")
                st.metric("1️⃣ Quality", f"{avg_preprocess:.2f}s" if avg_preprocess else "N/A")
            with col2:
                avg_p1 = timing_stats.get("avg_pass1")
                st.metric("2️⃣ Vision", f"{avg_p1:.2f}s" if avg_p1 else "N/A")
            with col3:
                avg_p2 = timing_stats.get("avg_pass2")
                st.metric("3️⃣ Normalize", f"{avg_p2:.2f}s" if avg_p2 else "N/A")
            with col4:
                avg_p3 = timing_stats.get("avg_pass3")
                st.metric("4️⃣ LLM Val", f"{avg_p3:.2f}s" if avg_p3 else "N/A")
            with col5:
                avg_p4 = timing_stats.get("avg_pass4", 0)
                st.metric("5️⃣ Panel", f"{avg_p4:.2f}s" if avg_p4 else "~0s")
            with col6:
                st.metric("6️⃣ Patient", "~0s")  # Very fast, not tracked
            with col7:
                avg_total = timing_stats.get("avg_total")
                st.metric("⏱️ Total", f"{avg_total:.2f}s" if avg_total else "N/A")
            
            # Timing breakdown bar chart
            recent_timings = timing_stats.get("recent_timings", [])
            
            if recent_timings:
                st.subheader("📊 Recent Processing Times")
                
                # Create stacked bar chart
                df = pd.DataFrame(recent_timings)
                df["doc_short"] = df["document_id"].str[:8] + "..."
                
                fig = go.Figure()
                
                # Step 1: Quality check
                fig.add_trace(go.Bar(
                    name='1. Quality', 
                    x=df["doc_short"], 
                    y=df.get("preprocessing", [0]*len(df)), 
                    marker_color='#636EFA'
                ))
                
                # Step 2: Vision Extraction
                fig.add_trace(go.Bar(
                    name='2. Vision', 
                    x=df["doc_short"], 
                    y=df.get("pass1_vision", [0]*len(df)), 
                    marker_color='#EF553B'
                ))
                
                # Step 3: Normalization
                fig.add_trace(go.Bar(
                    name='3. Normalize', 
                    x=df["doc_short"], 
                    y=df.get("pass2_structure", [0]*len(df)), 
                    marker_color='#00CC96'
                ))
                
                # Step 4: LLM Validation
                fig.add_trace(go.Bar(
                    name='4. LLM Val', 
                    x=df["doc_short"], 
                    y=df.get("pass3_standardize", [0]*len(df)), 
                    marker_color='#AB63FA'
                ))
                
                # Step 5: Panel Validation (using pass4 time if available)
                if "pass4_time" in df.columns:
                    fig.add_trace(go.Bar(
                        name='5. Panel', 
                        x=df["doc_short"], 
                        y=df.get("pass4_time", [0]*len(df)), 
                        marker_color='#FFA15A'
                    ))
                
                fig.update_layout(
                    barmode='stack',
                    xaxis_title='Document',
                    yaxis_title='Time (seconds)',
                    height=350,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(t=40, b=40, l=40, r=40)
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No timing data available yet. Process some documents to see timing metrics.")
    else:
        st.error(f"Error: {response.status_code}")
except requests.exceptions.RequestException as e:
    st.error(f"Connection error: {str(e)[:50]}")

st.divider()

# =============================================================================
# Recent Documents
# =============================================================================
st.subheader("📜 Recent Documents")

try:
    response = requests.get(f"{API_URL}/documents", timeout=5)
    if response.status_code == 200:
        documents = response.json()
        
        if documents:
            # Show last 10 documents
            recent = documents[:10]
            
            df = pd.DataFrame([
                {
                    "Filename": doc.get("filename", "N/A")[:40],
                    "Status": doc.get("status", "unknown"),
                    "Patient ID": doc.get("patient_id", "N/A")[:20] if doc.get("patient_id") else "Auto-generated",
                    "Upload Date": doc.get("upload_date", "N/A")[:19],
                }
                for doc in recent
            ])
            
            # Color-code status
            def color_status(status):
                if status == "completed":
                    return "background-color: #d4edda"
                elif status == "failed":
                    return "background-color: #f8d7da"
                elif status == "processing":
                    return "background-color: #fff3cd"
                return ""
            
            st.dataframe(
                df.style.map(lambda x: color_status(x) if x in ["completed", "failed", "processing"] else "", subset=["Status"]),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No documents processed yet.")
except requests.exceptions.RequestException as e:
    st.error(f"Connection error: {str(e)[:50]}")

# =============================================================================
# Footer
# =============================================================================
st.divider()
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
