"""
Performance Monitoring Page

Displays system performance metrics including:
- Rate limiter status
- Cache statistics
- Worker queue status
- Document processing metrics
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# API configuration
API_URL = "http://backend:6000/api/v1"

st.set_page_config(
    page_title="Performance Monitor",
    page_icon="📊",
    layout="wide"
)

st.title("📊 System Performance Monitor")
st.markdown("Real-time monitoring of system performance, rate limits, and processing metrics.")

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

# Create columns for metrics
col1, col2, col3 = st.columns(3)

# =============================================================================
# Rate Limiter Stats
# =============================================================================
with col1:
    st.subheader("⚡ Rate Limiter")
    try:
        response = requests.get(f"{API_URL}/rate-limit-stats", timeout=5)
        if response.status_code == 200:
            rate_stats = response.json()
            
            if rate_stats.get("rate_limiting_enabled"):
                current = rate_stats.get("current_requests", 0)
                effective_rpm = rate_stats.get("effective_rpm", 15)
                max_rpm = rate_stats.get("max_rpm", 15)
                is_throttled = rate_stats.get("is_throttled", False)
                
                # Status indicator
                if is_throttled:
                    st.error("🔴 Throttled")
                else:
                    st.success("🟢 Normal")
                
                # Metrics
                st.metric("Current Requests", current, delta=None)
                st.metric("Effective RPM", effective_rpm, 
                         delta=f"{effective_rpm - max_rpm}" if effective_rpm != max_rpm else None,
                         delta_color="inverse")
                st.metric("Max RPM", max_rpm)
                
                # Progress bar for rate limit usage
                usage_pct = min(current / effective_rpm * 100, 100) if effective_rpm > 0 else 0
                st.progress(usage_pct / 100, text=f"Usage: {usage_pct:.0f}%")
            else:
                st.warning("Rate limiting disabled")
        else:
            st.error(f"Error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        st.error(f"Connection error: {str(e)[:50]}")

# =============================================================================
# Cache Stats
# =============================================================================
with col2:
    st.subheader("💾 Cache Statistics")
    try:
        response = requests.get(f"{API_URL}/cache-stats", timeout=5)
        if response.status_code == 200:
            cache_stats = response.json()
            
            if cache_stats.get("cache_enabled"):
                redis_available = cache_stats.get("redis_available", False)
                
                if redis_available:
                    st.success("🟢 Redis Connected")
                else:
                    st.warning("🟡 Disk Cache Only")
                
                # Get nested stats
                stats = cache_stats.get("stats", cache_stats)
                
                redis_hits = stats.get("redis_hits", 0)
                redis_misses = stats.get("redis_misses", 0)
                disk_hits = stats.get("disk_hits", 0)
                disk_misses = stats.get("disk_misses", 0)
                
                total_hits = redis_hits + disk_hits
                total_requests = total_hits + redis_misses + disk_misses
                hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
                
                st.metric("Hit Rate", f"{hit_rate:.1f}%")
                st.metric("Redis Hits / Misses", f"{redis_hits} / {redis_misses}")
                st.metric("Disk Hits / Misses", f"{disk_hits} / {disk_misses}")
                st.metric("Total Cache Writes", stats.get("cache_writes", 0))
            else:
                st.warning("Caching disabled")
                if "error" in cache_stats:
                    st.caption(f"Error: {cache_stats['error']}")
        else:
            st.error(f"Error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        st.error(f"Connection error: {str(e)[:50]}")

# =============================================================================
# Document Stats
# =============================================================================
with col3:
    st.subheader("📄 Document Processing")
    try:
        response = requests.get(f"{API_URL}/documents", timeout=5)
        if response.status_code == 200:
            documents = response.json()
            
            # Count by status
            status_counts = {}
            for doc in documents:
                status = doc.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            total = len(documents)
            completed = status_counts.get("completed", 0)
            failed = status_counts.get("failed", 0)
            pending = status_counts.get("pending", 0) + status_counts.get("queued", 0)
            processing = status_counts.get("processing", 0)
            
            st.metric("Total Documents", total)
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("✅ Completed", completed)
                st.metric("⏳ Pending", pending)
            with col_b:
                st.metric("❌ Failed", failed)
                st.metric("🔄 Processing", processing)
            
            # Success rate
            if completed + failed > 0:
                success_rate = completed / (completed + failed) * 100
                st.progress(success_rate / 100, text=f"Success Rate: {success_rate:.0f}%")
        else:
            st.error(f"Error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        st.error(f"Connection error: {str(e)[:50]}")

st.divider()

# =============================================================================
# Test Statistics
# =============================================================================
st.subheader("🧪 Test Extraction Statistics")

try:
    response = requests.get(f"{API_URL}/tests/stats", timeout=5)
    if response.status_code == 200:
        test_stats = response.json()
        
        col_a, col_b, col_c, col_d = st.columns(4)
        
        with col_a:
            st.metric("Total Tests Extracted", test_stats.get("total_tests", 0))
        with col_b:
            st.metric("Unique Patients", test_stats.get("unique_patients", 0))
        with col_c:
            st.metric("Unique Test Types", test_stats.get("unique_test_types", 0))
        with col_d:
            rate = test_stats.get("standardization_rate", 0) * 100
            st.metric("Standardization Rate", f"{rate:.1f}%")
        
        # Match type distribution
        match_dist = test_stats.get("match_type_distribution", {})
        if match_dist:
            st.subheader("Match Type Distribution")
            
            # Create pie chart
            labels = list(match_dist.keys())
            values = list(match_dist.values())
            
            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.4,
                marker_colors=['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#3B1F2B']
            )])
            fig.update_layout(
                height=300,
                margin=dict(t=20, b=20, l=20, r=20)
            )
            st.plotly_chart(fig, use_container_width=True)
except requests.exceptions.RequestException as e:
    st.error(f"Connection error: {str(e)[:50]}")

st.divider()

# =============================================================================
# Processing Timing
# =============================================================================
st.subheader("⏱️ Processing Timing")

try:
    response = requests.get(f"{API_URL}/tests/timing-stats", timeout=5)
    if response.status_code == 200:
        timing_stats = response.json()
        
        total_processed = timing_stats.get("total_processed", 0)
        
        if total_processed > 0:
            # Average timing metrics
            col_a, col_b, col_c, col_d, col_e = st.columns(5)
            
            with col_a:
                avg_preprocess = timing_stats.get("avg_preprocessing")
                st.metric("Avg Preprocessing", f"{avg_preprocess:.2f}s" if avg_preprocess else "N/A")
            with col_b:
                avg_pass1 = timing_stats.get("avg_pass1")
                st.metric("Avg Pass 1 (Vision)", f"{avg_pass1:.2f}s" if avg_pass1 else "N/A")
            with col_c:
                avg_pass2 = timing_stats.get("avg_pass2")
                st.metric("Avg Pass 2 (Structure)", f"{avg_pass2:.2f}s" if avg_pass2 else "N/A")
            with col_d:
                avg_pass3 = timing_stats.get("avg_pass3")
                st.metric("Avg Pass 3 (Standardize)", f"{avg_pass3:.2f}s" if avg_pass3 else "N/A")
            with col_e:
                avg_total = timing_stats.get("avg_total")
                st.metric("Avg Total", f"{avg_total:.2f}s" if avg_total else "N/A")
            
            # Timing breakdown bar chart
            recent_timings = timing_stats.get("recent_timings", [])
            if recent_timings:
                st.subheader("Recent Document Processing Times")
                
                # Create stacked bar chart
                df = pd.DataFrame(recent_timings)
                df["doc_short"] = df["document_id"].str[:8] + "..."
                
                fig = go.Figure()
                fig.add_trace(go.Bar(name='Preprocessing', x=df["doc_short"], y=df["preprocessing"], marker_color='#1f77b4'))
                fig.add_trace(go.Bar(name='Pass 1 (Vision)', x=df["doc_short"], y=df["pass1_vision"], marker_color='#ff7f0e'))
                fig.add_trace(go.Bar(name='Pass 2 (Structure)', x=df["doc_short"], y=df["pass2_structure"], marker_color='#2ca02c'))
                fig.add_trace(go.Bar(name='Pass 3 (Standardize)', x=df["doc_short"], y=df["pass3_standardize"], marker_color='#d62728'))
                
                fig.update_layout(
                    barmode='stack',
                    xaxis_title='Document',
                    yaxis_title='Time (seconds)',
                    height=350,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(t=40, b=40, l=40, r=40)
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Show timing table
                st.subheader("Timing Details")
                timing_df = pd.DataFrame(recent_timings)[["document_id", "preprocessing", "pass1_vision", "pass2_structure", "pass3_standardize", "total", "confidence"]]
                timing_df.columns = ["Document ID", "Preprocess (s)", "Vision (s)", "Structure (s)", "Standardize (s)", "Total (s)", "Confidence"]
                st.dataframe(timing_df, use_container_width=True, hide_index=True)
        else:
            st.info("No timing data available yet. Process some documents to see timing metrics.")
    else:
        st.error(f"Error: {response.status_code}")
except requests.exceptions.RequestException as e:
    st.error(f"Connection error: {str(e)[:50]}")

st.divider()

# =============================================================================
# Recent Activity Log
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
