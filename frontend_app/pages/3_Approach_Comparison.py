"""
Approach Comparison Page.

Allows users to upload a document and compare Vision-Only vs Three-Tier extraction approaches.
"""
import os
import streamlit as st
import requests
import pandas as pd
import time

# API URL - use environment variable in Docker, fallback to localhost
API_URL = os.environ.get("API_URL", "http://localhost:6000/api/v1")

st.set_page_config(
    page_title="Approach Comparison",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Extraction Approach Comparison")
st.caption("Compare Vision-Only (single pass) vs Three-Tier (4-pass) extraction approaches")

st.markdown("""
### How it works
- **Vision-Only**: Single API call - image directly to structured JSON
- **Three-Tier (4-Pass)**: 
  - Pass 1: Vision extraction → raw text
  - Pass 2: Structure + Validate → JSON
  - Pass 3: Standardize test names → LOINC codes
  - Pass 4: Generate summary → clinical recommendations
""")

st.markdown("---")

# File upload
uploaded_file = st.file_uploader(
    "Upload a lab report image to compare",
    type=["jpg", "jpeg", "png", "pdf"],
    help="Upload a lab report image to run both extraction approaches"
)

if uploaded_file:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.image(uploaded_file, caption="Uploaded Document", use_container_width=True)
    
    with col2:
        if st.button("🔬 Run Comparison", type="primary"):
            # Create status containers for live updates
            status_container = st.container()
            
            with status_container:
                st.markdown("### 🔄 Running Comparison...")
                
                # Stage progress display
                stage_cols = st.columns(2)
                
                with stage_cols[0]:
                    st.markdown("**Vision-Only Approach:**")
                    vision_status = st.empty()
                    vision_status.info("⏳ Pending...")
                
                with stage_cols[1]:
                    st.markdown("**Three-Tier Approach:**")
                    tier_status = st.empty()
                    tier_status.info("⏳ Pending...")
                
                progress_bar = st.progress(0)
                stage_text = st.empty()
            
            start_time = time.time()
            
            try:
                # Update stage display
                vision_status.warning("🔄 Running Vision-Only extraction...")
                stage_text.text("Stage 1/2: Vision-Only extraction in progress...")
                progress_bar.progress(10)
                
                # Call the comparison API  
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                
                # Note: The API runs both approaches sequentially
                # We can't get real-time stage updates from the API, but we show estimated progress
                progress_bar.progress(25)
                stage_text.text("Stage 1/2: Processing image with Vision-Only approach...")
                
                response = requests.post(f"{API_URL}/compare-approaches", files=files, timeout=300)
                
                progress_bar.progress(100)
                stage_text.text("Complete!")
                
                if response.status_code == 200:
                    data = response.json()
                    comparison = data.get("comparison", {})
                    
                    # Update status display
                    vision_status.success("✅ Complete")
                    tier_status.success("✅ Complete")
                    
                    st.success(f"✅ Comparison complete in {time.time() - start_time:.1f}s")
                    
                    # Display results
                    results = comparison.get("results", [])
                    
                    if results:
                        st.subheader("📊 Comparison Results")
                        
                        # Build comparison table
                        table_data = []
                        for r in results:
                            table_data.append({
                                "Approach": r.get("approach_name", "Unknown"),
                                "Success": "✅" if r.get("success") else "❌",
                                "Time (s)": f"{r.get('extraction_time', 0):.2f}",
                                "Confidence": f"{r.get('confidence_score', 0):.1%}",
                                "Tests Extracted": r.get("tests_extracted", 0),
                                "Error": r.get("error", "-") or "-"
                            })
                        
                        st.dataframe(pd.DataFrame(table_data), use_container_width=True)
                        
                        # Speed comparison chart
                        times = [r.get("extraction_time", 0) for r in results]
                        names = [r.get("approach_name", "Unknown") for r in results]
                        
                        if all(t > 0 for t in times):
                            st.subheader("⏱️ Processing Time Comparison")
                            chart_df = pd.DataFrame({
                                "Approach": names,
                                "Time (seconds)": times
                            })
                            st.bar_chart(chart_df.set_index("Approach"))
                        
                        # Display 3-Level Diff Analysis
                        diff = comparison.get("diff")
                        if diff:
                            st.subheader("🔍 Extraction Diff Analysis")
                            
                            summary = diff.get("summary", {})
                            safe_count = summary.get("safe_count", 0)
                            suspicious_count = summary.get("suspicious_count", 0)
                            hallucinated_count = summary.get("hallucinated_count", 0)
                            
                            # Display badges
                            badge_cols = st.columns(3)
                            
                            with badge_cols[0]:
                                if safe_count > 0:
                                    st.success(f"🟢 **{safe_count}** Safe Matches")
                                else:
                                    st.info(f"🟢 {safe_count} Safe Matches")
                            
                            with badge_cols[1]:
                                if suspicious_count > 0:
                                    st.warning(f"🟡 **{suspicious_count}** Suspicious Values")
                                else:
                                    st.info(f"🟡 {suspicious_count} Suspicious")
                            
                            with badge_cols[2]:
                                if hallucinated_count > 0:
                                    st.error(f"🔴 **{hallucinated_count}** Hallucinated Tests!")
                                else:
                                    st.info(f"🔴 {hallucinated_count} Hallucinated")
                            
                            # Expandable details
                            if hallucinated_count > 0:
                                with st.expander("🔴 View Hallucinated Tests", expanded=True):
                                    st.markdown("**Tests found in Three-Tier but NOT in Vision-Only:**")
                                    for item in diff.get("hallucinated", []):
                                        st.markdown(f"- ❌ **{item.get('test_name')}**: {item.get('value')} — *{item.get('reason')}*")
                            
                            if suspicious_count > 0:
                                with st.expander("🟡 View Suspicious Values"):
                                    st.markdown("**Values that differ significantly between approaches:**")
                                    for item in diff.get("suspicious", []):
                                        st.markdown(f"- ⚠️ **{item.get('test_name')}**: Vision={item.get('vision_value')} vs Tier={item.get('tier_value')}")
                            
                            if safe_count > 0:
                                with st.expander("🟢 View Safe Matches"):
                                    st.markdown("**Values that match between both approaches:**")
                                    for item in diff.get("safe_matches", [])[:10]:  # Limit to 10
                                        st.markdown(f"- ✅ **{item.get('test_name')}**: {item.get('vision_value')}")
                                    if safe_count > 10:
                                        st.caption(f"...and {safe_count - 10} more")
                        
                        # Detailed results
                        st.subheader("📋 Detailed Results")
                        
                        tabs = st.tabs([r.get("approach_name", f"Approach {i+1}") for i, r in enumerate(results)])
                        
                        for i, (tab, result) in enumerate(zip(tabs, results)):
                            with tab:
                                if result.get("success"):
                                    data = result.get("data", {})
                                    
                                    # Summary section
                                    summary = result.get("summary") or data.get("summary", {})
                                    if summary:
                                        st.markdown("**Report Summary:**")
                                        st.write(f"- **Type:** {summary.get('report_type', 'N/A')}")
                                        st.write(f"- **Purpose:** {summary.get('report_purpose', 'N/A')}")
                                        
                                        priority = summary.get("priority_level", "normal")
                                        priority_colors = {"urgent": "🔴", "attention": "🟡", "normal": "🟢"}
                                        st.write(f"- **Priority:** {priority_colors.get(priority, '')} {priority.title()}")
                                        
                                        abnormal = summary.get("abnormal_findings", [])
                                        if abnormal:
                                            st.write("- **Abnormal Findings:**")
                                            for f in abnormal:
                                                st.write(f"  - ⚠️ {f}")
                                    
                                    # Lab results table
                                    lab_results = data.get("lab_results", [])
                                    if lab_results:
                                        st.markdown(f"**Lab Results ({len(lab_results)} tests):**")
                                        results_df = pd.DataFrame([
                                            {
                                                "Test": r.get("test_name", r.get("original_name", "")),
                                                "Value": r.get("value", ""),
                                                "Unit": r.get("unit", ""),
                                                "Reference": r.get("reference_range", ""),
                                                "Flag": r.get("flag", "")
                                            }
                                            for r in lab_results[:20]  # Limit to 20
                                        ])
                                        st.dataframe(results_df, use_container_width=True)
                                        
                                        if len(lab_results) > 20:
                                            st.caption(f"Showing 20 of {len(lab_results)} results")
                                    
                                    # Raw data expander
                                    with st.expander("View Raw JSON"):
                                        st.json(data)
                                else:
                                    st.error(f"Extraction failed: {result.get('error', 'Unknown error')}")
                    else:
                        st.warning("No comparison results returned")
                else:
                    vision_status.error("❌ Failed")
                    tier_status.error("❌ Failed")
                    st.error(f"API error: {response.text}")
                    
            except requests.exceptions.Timeout:
                vision_status.error("❌ Timeout")
                tier_status.error("❌ Timeout")
                st.error("Request timed out. The extraction is taking too long.")
            except requests.exceptions.ConnectionError:
                vision_status.error("❌ Connection Error")
                tier_status.error("❌ Connection Error")
                st.error(f"Cannot connect to backend at {API_URL}")
            except Exception as e:
                st.error(f"Error: {str(e)}")
else:
    st.info("👆 Upload a lab report image above to compare extraction approaches")

# Information section
st.markdown("---")
st.subheader("ℹ️ About the Approaches")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **Vision-Only (Single Pass)**
    - 🚀 Faster (1 API call)
    - ⚡ Lower latency
    - 💰 Lower cost
    - ⚠️ May miss some standardization
    """)

with col2:
    st.markdown("""
    **Three-Tier (4-Pass)**
    - 🎯 Higher accuracy
    - 🏷️ LOINC code mapping
    - 📋 Clinical summaries
    - 🔍 Better standardization
    """)
