"""
Locust load testing configuration.
Run with: locust -f tests/performance/locustfile.py
"""
from locust import HttpUser, task, between, tag


class RegularUser(HttpUser):
    """
    Simulates a regular user uploading and checking documents.
    """
    weight = 3  # Most common user type
    wait_time = between(1, 5)  # Wait 1-5 seconds between tasks
    
    @task(3)
    @tag("read")
    def get_documents(self):
        """Fetch document list - most common operation."""
        self.client.get("/api/v1/documents")
    
    @task(2)
    @tag("read")
    def get_document_status(self):
        """Check status of a specific document."""
        # Use a test document ID
        self.client.get("/api/v1/documents/test-doc-123")
    
    @task(1)
    @tag("write")
    def upload_document(self):
        """Upload a document - less frequent."""
        # Create a minimal test image
        import io
        from PIL import Image
        
        img = Image.new('RGB', (100, 100), color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        self.client.post(
            "/api/v1/upload",
            files={"files": ("test.png", buffer, "image/png")}
        )
    
    @task(2)
    @tag("read")
    def get_extraction_result(self):
        """Fetch extraction results."""
        self.client.get("/api/v1/results/test-doc-123")


class PowerUser(HttpUser):
    """
    Simulates a power user doing batch operations.
    """
    weight = 1  # Less common
    wait_time = between(0.5, 2)  # More active
    
    @task(2)
    @tag("write")
    def batch_upload(self):
        """Upload multiple documents at once."""
        import io
        from PIL import Image
        
        files = []
        for i in range(3):
            img = Image.new('RGB', (100, 100), color='white')
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            files.append(("files", (f"test_{i}.png", buffer, "image/png")))
        
        self.client.post("/api/v1/upload", files=files)
    
    @task(3)
    @tag("read")
    def get_all_documents(self):
        """Fetch all documents with details."""
        self.client.get("/api/v1/documents")
    
    @task(1)
    @tag("read")
    def export_data(self):
        """Export data - heavy operation."""
        self.client.get("/api/v1/export")


class AnalyticsUser(HttpUser):
    """
    Simulates a user focused on analytics and monitoring.
    """
    weight = 1
    wait_time = between(2, 10)  # Less frequent checks
    
    @task(3)
    @tag("analytics")
    def get_analytics(self):
        """Fetch analytics data."""
        self.client.get("/api/v1/analytics")
    
    @task(2)
    @tag("analytics")
    def get_cache_stats(self):
        """Check cache statistics."""
        self.client.get("/api/v1/cache/stats")
    
    @task(1)
    @tag("analytics")
    def get_flagged_documents(self):
        """Check documents needing review."""
        self.client.get("/api/v1/documents/flagged")
    
    @task(1)
    @tag("health")
    def health_check(self):
        """Check system health."""
        self.client.get("/docs")
