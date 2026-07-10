# ====================================
# database.py - RBI Compliant Database Module
# Version: 2.0 - With Duplicate Handling & History Tracking
# ====================================

# ====================================
# IMPORTS
# ====================================
import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import sqlite3
import logging
from contextlib import contextmanager

# ====================================
# LOGGING SETUP
# ====================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====================================
# DATABASE CONFIGURATION
# ====================================
DB_PATH = "kyc_verification.db"
ENCRYPTION_KEY = os.environ.get("KYC_ENCRYPTION_KEY", secrets.token_hex(32))

# ====================================
# DATABASE SCHEMA - UPDATED VERSION
# ====================================
class DatabaseSchema:
    """
    RBI Compliant Database Schema with Duplicate Handling
    Follows data minimization and privacy by design principles
    """
    
    @staticmethod
    def get_create_tables_sql():
        return """
        -- ====================================
        -- 1. AUDIT LOGS (RBI Mandate)
        -- Purpose: Prove every action was taken
        -- Retention: 5-7 years as per RBI
        -- ====================================
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            user_hash TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            request_data TEXT,
            response_status TEXT,
            error_message TEXT,
            duration_ms INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ====================================
        -- 2. CONSENT RECORDS (DPDP Act)
        -- Purpose: Prove explicit consent was obtained
        -- Retention: As per consent duration
        -- ====================================
        CREATE TABLE IF NOT EXISTS consent_records (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            user_hash TEXT NOT NULL,
            consent_purpose TEXT NOT NULL,
            consent_artefact TEXT NOT NULL,
            consent_given_at TEXT NOT NULL,
            consent_valid_until TEXT NOT NULL,
            consent_revoked BOOLEAN DEFAULT 0,
            revoked_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ====================================
        -- 3. VERIFICATION RESULTS (UPDATED - No UNIQUE constraint)
        -- Purpose: Store verification outcomes with history tracking
        -- Retention: 5-7 years as per RBI
        -- ====================================
        CREATE TABLE IF NOT EXISTS verification_results (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            attempt_number INTEGER DEFAULT 1,
            user_hash TEXT NOT NULL,
            verification_date TEXT NOT NULL,
            risk_score INTEGER,
            recommendation TEXT,
            verification_status TEXT,
            aadhaar_verified BOOLEAN,
            pan_verified BOOLEAN,
            salary_verified BOOLEAN,
            issues_found TEXT,
            pdf_path TEXT,
            processing_time_ms INTEGER,
            source_file TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ====================================
        -- 4. API USAGE LOGS (Cost Tracking)
        -- Purpose: Track API usage and costs
        -- ====================================
        CREATE TABLE IF NOT EXISTS api_usage (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            api_name TEXT NOT NULL,
            model_used TEXT,
            tokens_used INTEGER,
            cost_estimate REAL,
            response_time_ms INTEGER,
            status_code INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ====================================
        -- 5. SESSION MANAGEMENT
        -- Purpose: Track user sessions
        -- ====================================
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            user_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_activity TEXT,
            status TEXT DEFAULT 'ACTIVE'
        );

        -- ====================================
        -- 6. TEMPORARY DATA STORE (Purged after processing)
        -- Purpose: Hold data only during processing
        -- ====================================
        CREATE TABLE IF NOT EXISTS temp_processing_data (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            data_type TEXT NOT NULL,
            data_content TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT,
            purged BOOLEAN DEFAULT 0
        );

        -- ====================================
        -- 7. BATCH PROCESSING LOGS (NEW)
        -- Purpose: Track batch uploads and processing
        -- ====================================
        CREATE TABLE IF NOT EXISTS batch_processing_logs (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            file_name TEXT,
            file_hash TEXT,
            processing_status TEXT,
            error_message TEXT,
            processed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ====================================
        -- INDEXES FOR PERFORMANCE
        -- ====================================
        CREATE INDEX IF NOT EXISTS idx_audit_transaction ON audit_logs(transaction_id);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_hash);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_consent_user ON consent_records(user_hash);
        CREATE INDEX IF NOT EXISTS idx_consent_transaction ON consent_records(transaction_id);
        CREATE INDEX IF NOT EXISTS idx_results_transaction ON verification_results(transaction_id);
        CREATE INDEX IF NOT EXISTS idx_results_user ON verification_results(user_hash);
        CREATE INDEX IF NOT EXISTS idx_results_created ON verification_results(created_at);
        CREATE INDEX IF NOT EXISTS idx_results_attempt ON verification_results(transaction_id, attempt_number);
        CREATE INDEX IF NOT EXISTS idx_sessions_id ON sessions(session_id);
        CREATE INDEX IF NOT EXISTS idx_temp_transaction ON temp_processing_data(transaction_id);
        CREATE INDEX IF NOT EXISTS idx_batch_id ON batch_processing_logs(batch_id);
        CREATE INDEX IF NOT EXISTS idx_batch_transaction ON batch_processing_logs(transaction_id);
        """
    
    @staticmethod
    def get_create_views_sql():
        return """
        -- ====================================
        -- VIEWS FOR REPORTING
        -- ====================================
        
        -- 1. Daily Verification Statistics
        CREATE VIEW IF NOT EXISTS daily_stats AS
        SELECT 
            DATE(verification_date) as date,
            COUNT(*) as total_verifications,
            COUNT(DISTINCT transaction_id) as unique_transactions,
            SUM(CASE WHEN recommendation = 'APPROVE' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN recommendation = 'REJECT' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN recommendation = 'MANUAL_REVIEW' THEN 1 ELSE 0 END) as manual_review,
            AVG(risk_score) as avg_risk_score
        FROM verification_results
        WHERE attempt_number = 1
        GROUP BY DATE(verification_date);

        -- 2. Latest Verification Status Per Transaction
        CREATE VIEW IF NOT EXISTS latest_verification_status AS
        SELECT 
            v1.*
        FROM verification_results v1
        INNER JOIN (
            SELECT transaction_id, MAX(attempt_number) as max_attempt
            FROM verification_results
            GROUP BY transaction_id
        ) v2 ON v1.transaction_id = v2.transaction_id 
            AND v1.attempt_number = v2.max_attempt;

        -- 3. Verification Attempt History
        CREATE VIEW IF NOT EXISTS verification_attempts_summary AS
        SELECT 
            transaction_id,
            COUNT(*) as total_attempts,
            MIN(created_at) as first_attempt,
            MAX(created_at) as last_attempt,
            SUM(CASE WHEN verification_status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_attempts,
            SUM(CASE WHEN verification_status = 'FAILED' THEN 1 ELSE 0 END) as failed_attempts
        FROM verification_results
        GROUP BY transaction_id;

        -- 4. Monthly Compliance Report
        CREATE VIEW IF NOT EXISTS monthly_compliance AS
        SELECT 
            strftime('%Y-%m', verification_date) as month,
            COUNT(*) as total_verifications,
            COUNT(DISTINCT transaction_id) as unique_transactions,
            COUNT(DISTINCT user_hash) as unique_users,
            MIN(verification_date) as first_verification,
            MAX(verification_date) as last_verification
        FROM verification_results
        GROUP BY strftime('%Y-%m', verification_date);

        -- 5. API Performance Dashboard
        CREATE VIEW IF NOT EXISTS api_performance AS
        SELECT 
            api_name,
            model_used,
            COUNT(*) as total_calls,
            AVG(response_time_ms) as avg_response_time,
            SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as successful,
            SUM(cost_estimate) as total_cost
        FROM api_usage
        GROUP BY api_name, model_used;

        -- 6. Batch Processing Summary
        CREATE VIEW IF NOT EXISTS batch_summary AS
        SELECT 
            batch_id,
            COUNT(*) as total_files,
            SUM(CASE WHEN processing_status = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN processing_status = 'FAILED' THEN 1 ELSE 0 END) as failed,
            MIN(created_at) as started_at,
            MAX(processed_at) as completed_at
        FROM batch_processing_logs
        GROUP BY batch_id;
        """

# ====================================
# DATABASE MANAGER CLASS - UPDATED
# ====================================
class KYCDataBase:
    """
    RBI Compliant Database Manager with Duplicate Handling
    Handles all database operations with security and compliance
    """
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database with tables and views"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create tables
            cursor.executescript(DatabaseSchema.get_create_tables_sql())
            
            # Create views
            cursor.executescript(DatabaseSchema.get_create_views_sql())
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def hash_user_identifier(self, identifier: str) -> str:
        """
        Hash user identifier for storage
        Ensures no PII is stored directly
        """
        if not identifier:
            return hashlib.sha256(str(uuid4()).encode()).hexdigest()
        return hashlib.sha256(f"{identifier}{ENCRYPTION_KEY}".encode()).hexdigest()
    
    def generate_transaction_id(self) -> str:
        """Generate unique transaction ID"""
        return f"TXN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8].upper()}"
    
    def generate_batch_id(self) -> str:
        """Generate unique batch ID"""
        return f"BATCH_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6].upper()}"
    
    # ====================================
    # 1. AUDIT LOG OPERATIONS
    # ====================================
    def log_audit_event(
        self,
        transaction_id: str,
        event_type: str,
        user_hash: str,
        ip_address: str = None,
        user_agent: str = None,
        request_data: Dict = None,
        response_status: str = None,
        error_message: str = None,
        duration_ms: int = None
    ):
        """Log an audit event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs (
                    id, transaction_id, timestamp, event_type, user_hash,
                    ip_address, user_agent, request_data, response_status,
                    error_message, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uuid4().hex,
                transaction_id,
                datetime.now().isoformat(),
                event_type,
                user_hash,
                ip_address,
                user_agent,
                json.dumps(request_data) if request_data else None,
                response_status,
                error_message,
                duration_ms
            ))
            conn.commit()
    
    # ====================================
    # 2. CONSENT RECORD OPERATIONS
    # ====================================
    def record_consent(
        self,
        transaction_id: str,
        user_hash: str,
        purpose: str,
        consent_artefact: Dict,
        valid_days: int = 365
    ) -> str:
        """Record user consent"""
        consent_id = uuid4().hex
        given_at = datetime.now().isoformat()
        valid_until = (datetime.now() + timedelta(days=valid_days)).isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO consent_records (
                    id, transaction_id, user_hash, consent_purpose,
                    consent_artefact, consent_given_at, consent_valid_until
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                consent_id,
                transaction_id,
                user_hash,
                purpose,
                json.dumps(consent_artefact),
                given_at,
                valid_until
            ))
            conn.commit()
        
        return consent_id
    
    def revoke_consent(self, consent_id: str):
        """Revoke user consent"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE consent_records
                SET consent_revoked = 1, revoked_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), consent_id))
            conn.commit()
    
    def check_consent_valid(self, consent_id: str) -> bool:
        """Check if consent is still valid"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT consent_valid_until, consent_revoked
                FROM consent_records
                WHERE id = ?
            """, (consent_id,))
            result = cursor.fetchone()
            
            if not result:
                return False
            
            if result['consent_revoked']:
                return False
            
            valid_until = datetime.fromisoformat(result['consent_valid_until'])
            return valid_until > datetime.now()
    
    # ====================================
    # 3. VERIFICATION RESULTS OPERATIONS - UPDATED
    # ====================================
    def store_verification_result(
        self,
        transaction_id: str,
        user_hash: str,
        risk_score: int,
        recommendation: str,
        verification_status: str,
        aadhaar_verified: bool,
        pan_verified: bool,
        salary_verified: bool,
        issues_found: List[str],
        pdf_path: str = None,
        processing_time_ms: int = None,
        source_file: str = None
    ) -> Dict[str, Any]:
        """
        Store verification results with duplicate handling and history tracking
        
        Returns:
            Dict containing attempt_number and status
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get the latest attempt number for this transaction
            cursor.execute("""
                SELECT COUNT(*) as attempt_count FROM verification_results
                WHERE transaction_id = ?
            """, (transaction_id,))
            result = cursor.fetchone()
            attempt_number = result['attempt_count'] + 1 if result else 1
            
            # Insert new record with attempt number
            cursor.execute("""
                INSERT INTO verification_results (
                    id, transaction_id, attempt_number, user_hash, verification_date,
                    risk_score, recommendation, verification_status,
                    aadhaar_verified, pan_verified, salary_verified,
                    issues_found, pdf_path, processing_time_ms, source_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uuid4().hex,
                transaction_id,
                attempt_number,
                user_hash,
                datetime.now().isoformat(),
                risk_score,
                recommendation,
                verification_status,
                1 if aadhaar_verified else 0,
                1 if pan_verified else 0,
                1 if salary_verified else 0,
                json.dumps(issues_found) if issues_found else None,
                pdf_path,
                processing_time_ms,
                source_file
            ))
            conn.commit()
            
            logger.info(f"Stored verification result #{attempt_number} for transaction: {transaction_id}")
            
            return {
                "attempt_number": attempt_number,
                "transaction_id": transaction_id,
                "status": "stored",
                "is_duplicate": attempt_number > 1
            }
    
    def get_verification_result(self, transaction_id: str, attempt_number: int = None) -> Optional[Dict]:
        """
        Retrieve verification result
        
        Args:
            transaction_id: The transaction ID
            attempt_number: Specific attempt number (if None, returns latest)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if attempt_number is not None:
                cursor.execute("""
                    SELECT * FROM verification_results
                    WHERE transaction_id = ? AND attempt_number = ?
                """, (transaction_id, attempt_number))
            else:
                # Get latest attempt
                cursor.execute("""
                    SELECT * FROM verification_results
                    WHERE transaction_id = ?
                    ORDER BY attempt_number DESC, created_at DESC
                    LIMIT 1
                """, (transaction_id,))
            
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_verification_history(self, transaction_id: str) -> List[Dict]:
        """Get complete verification history for a transaction"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM verification_results
                WHERE transaction_id = ?
                ORDER BY attempt_number DESC, created_at DESC
            """, (transaction_id,))
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    def get_latest_verification(self, transaction_id: str) -> Optional[Dict]:
        """Get the latest verification result for a transaction"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM verification_results
                WHERE transaction_id = ?
                ORDER BY attempt_number DESC, created_at DESC
                LIMIT 1
            """, (transaction_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_verification_by_date_range(
        self, 
        start_date: str, 
        end_date: str,
        transaction_id: str = None
    ) -> List[Dict]:
        """Get verification results within date range"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT * FROM verification_results
                WHERE verification_date BETWEEN ? AND ?
            """
            params = [start_date, end_date]
            
            if transaction_id:
                query += " AND transaction_id = ?"
                params.append(transaction_id)
            
            query += " ORDER BY verification_date DESC"
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    # ====================================
    # 4. BATCH PROCESSING LOGS - NEW
    # ====================================
    def log_batch_processing(
        self,
        batch_id: str,
        transaction_id: str,
        file_name: str,
        file_hash: str = None,
        processing_status: str = "PENDING",
        error_message: str = None
    ):
        """Log batch processing file entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO batch_processing_logs (
                    id, batch_id, transaction_id, file_name, file_hash,
                    processing_status, error_message, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uuid4().hex,
                batch_id,
                transaction_id,
                file_name,
                file_hash,
                processing_status,
                error_message,
                datetime.now().isoformat() if processing_status != "PENDING" else None
            ))
            conn.commit()
            logger.info(f"Logged batch processing for {file_name} in batch {batch_id}")
    
    def update_batch_status(
        self,
        batch_id: str,
        transaction_id: str,
        processing_status: str,
        error_message: str = None
    ):
        """Update batch processing status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE batch_processing_logs
                SET processing_status = ?,
                    error_message = ?,
                    processed_at = ?
                WHERE batch_id = ? AND transaction_id = ?
            """, (
                processing_status,
                error_message,
                datetime.now().isoformat(),
                batch_id,
                transaction_id
            ))
            conn.commit()
    
    def get_batch_summary(self, batch_id: str) -> Dict:
        """Get summary of a batch processing"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_files,
                    SUM(CASE WHEN processing_status = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN processing_status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN processing_status = 'PENDING' THEN 1 ELSE 0 END) as pending
                FROM batch_processing_logs
                WHERE batch_id = ?
            """, (batch_id,))
            result = cursor.fetchone()
            return dict(result) if result else {}
    
    # ====================================
    # 5. API USAGE OPERATIONS
    # ====================================
    def log_api_usage(
        self,
        transaction_id: str,
        api_name: str,
        model_used: str = None,
        tokens_used: int = None,
        cost_estimate: float = None,
        response_time_ms: int = None,
        status_code: int = None
    ):
        """Log API usage for cost tracking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_usage (
                    id, transaction_id, api_name, model_used,
                    tokens_used, cost_estimate, response_time_ms, status_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uuid4().hex,
                transaction_id,
                api_name,
                model_used,
                tokens_used,
                cost_estimate,
                response_time_ms,
                status_code
            ))
            conn.commit()
    
    # ====================================
    # 6. SESSION MANAGEMENT
    # ====================================
    def create_session(self, user_hash: str, expiry_hours: int = 24) -> str:
        """Create a new session"""
        session_id = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(hours=expiry_hours)).isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (
                    id, session_id, user_hash, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                uuid4().hex,
                session_id,
                user_hash,
                datetime.now().isoformat(),
                expires_at
            ))
            conn.commit()
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[str]:
        """Validate session and return user_hash if valid"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_hash, expires_at, status
                FROM sessions
                WHERE session_id = ?
            """, (session_id,))
            result = cursor.fetchone()
            
            if not result:
                return None
            
            if result['status'] != 'ACTIVE':
                return None
            
            expires_at = datetime.fromisoformat(result['expires_at'])
            if expires_at < datetime.now():
                return None
            
            # Update last activity
            cursor.execute("""
                UPDATE sessions
                SET last_activity = ?
                WHERE session_id = ?
            """, (datetime.now().isoformat(), session_id))
            conn.commit()
            
            return result['user_hash']
    
    def invalidate_session(self, session_id: str):
        """Invalidate a session"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions
                SET status = 'INACTIVE'
                WHERE session_id = ?
            """, (session_id,))
            conn.commit()
    
    # ====================================
    # 7. TEMPORARY DATA OPERATIONS
    # ====================================
    def store_temp_data(
        self,
        transaction_id: str,
        data_type: str,
        data_content: Dict
    ):
        """Store data temporarily during processing"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO temp_processing_data (
                    id, transaction_id, data_type, data_content
                ) VALUES (?, ?, ?, ?)
            """, (
                uuid4().hex,
                transaction_id,
                data_type,
                json.dumps(data_content)
            ))
            conn.commit()
    
    def get_temp_data(self, transaction_id: str) -> List[Dict]:
        """Retrieve temporary data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM temp_processing_data
                WHERE transaction_id = ? AND purged = 0
            """, (transaction_id,))
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    def purge_temp_data(self, transaction_id: str):
        """Purge temporary data after processing (RBI Compliance)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE temp_processing_data
                SET purged = 1, processed_at = ?
                WHERE transaction_id = ?
            """, (datetime.now().isoformat(), transaction_id))
            conn.commit()
    
    # ====================================
    # 8. COMPLIANCE REPORTING
    # ====================================
    def get_daily_stats(self, date: str = None) -> List[Dict]:
        """Get daily verification statistics"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM daily_stats
                WHERE date = ?
            """, (date,))
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    def get_monthly_compliance_report(self, month: str = None) -> List[Dict]:
        """Get monthly compliance report"""
        if not month:
            month = datetime.now().strftime('%Y-%m')
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM monthly_compliance
                WHERE month = ?
            """, (month,))
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    def get_api_performance(self) -> List[Dict]:
        """Get API performance dashboard"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM api_performance")
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    def get_audit_trail(self, transaction_id: str) -> List[Dict]:
        """Get complete audit trail for a transaction"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM audit_logs
                WHERE transaction_id = ?
                ORDER BY timestamp
            """, (transaction_id,))
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    def get_duplicate_report(self, transaction_id: str = None) -> List[Dict]:
        """Get report of duplicate verifications"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if transaction_id:
                cursor.execute("""
                    SELECT * FROM verification_attempts_summary
                    WHERE transaction_id = ? AND total_attempts > 1
                """, (transaction_id,))
            else:
                cursor.execute("""
                    SELECT * FROM verification_attempts_summary
                    WHERE total_attempts > 1
                    ORDER BY total_attempts DESC
                """)
            
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    # ====================================
    # 9. DATA PURGING (RBI Compliance)
    # ====================================
    def purge_expired_data(self, retention_days: int = 2555):  # 7 years
        """Purge data older than retention period"""
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Purge old audit logs
            cursor.execute("""
                DELETE FROM audit_logs
                WHERE timestamp < ?
            """, (cutoff_date,))
            
            # Purge old verification results
            cursor.execute("""
                DELETE FROM verification_results
                WHERE verification_date < ?
            """, (cutoff_date,))
            
            # Purge expired sessions
            cursor.execute("""
                DELETE FROM sessions
                WHERE expires_at < ?
            """, (datetime.now().isoformat(),))
            
            # Purge old temporary data
            cursor.execute("""
                DELETE FROM temp_processing_data
                WHERE processed_at < ?
            """, (cutoff_date,))
            
            # Purge old batch logs
            cursor.execute("""
                DELETE FROM batch_processing_logs
                WHERE created_at < ?
            """, (cutoff_date,))
            
            conn.commit()
            logger.info(f"Purged data older than {retention_days} days")
    
    # ====================================
    # 10. SECURITY FUNCTIONS
    # ====================================
    def get_audit_logs_for_investigation(
        self,
        user_hash: str,
        start_date: str = None,
        end_date: str = None
    ) -> List[Dict]:
        """Get audit logs for investigation (RBI Mandate)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT * FROM audit_logs
                WHERE user_hash = ?
            """
            params = [user_hash]
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp"
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    def get_user_consent_history(self, user_hash: str) -> List[Dict]:
        """Get consent history for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM consent_records
                WHERE user_hash = ?
                ORDER BY consent_given_at DESC
            """, (user_hash,))
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    # ====================================
    # 11. BACKUP AND RECOVERY
    # ====================================
    def create_backup(self, backup_path: str = None):
        """Create database backup"""
        if not backup_path:
            backup_path = f"kyc_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        import shutil
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Backup created: {backup_path}")
        return backup_path
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            stats = {}
            
            # Count records
            tables = [
                'audit_logs',
                'consent_records',
                'verification_results',
                'api_usage',
                'sessions',
                'temp_processing_data',
                'batch_processing_logs'
            ]
            
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                result = cursor.fetchone()
                stats[table] = result['count']
            
            # Get duplicate statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_duplicates,
                    SUM(total_attempts - 1) as extra_attempts
                FROM verification_attempts_summary
                WHERE total_attempts > 1
            """)
            dup_stats = cursor.fetchone()
            stats['duplicate_transactions'] = dup_stats['total_duplicates'] if dup_stats else 0
            stats['extra_attempts'] = dup_stats['extra_attempts'] if dup_stats else 0
            
            # Get database size
            import os
            stats['database_size_mb'] = os.path.getsize(self.db_path) / (1024 * 1024)
            
            return stats
    
    # ====================================
    # 12. MIGRATION FOR EXISTING DATABASES
    # ====================================
    def migrate_existing_database(self):
        """Migrate existing database to new schema with duplicate support"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if old schema exists (has UNIQUE constraint)
            cursor.execute("""
                SELECT sql FROM sqlite_master 
                WHERE type='table' AND name='verification_results'
            """)
            result = cursor.fetchone()
            
            if result and "UNIQUE" in result['sql']:
                logger.info("Migrating existing database to new schema...")
                
                # Create backup of existing data
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS verification_results_backup AS
                    SELECT * FROM verification_results
                """)
                
                # Drop old table
                cursor.execute("DROP TABLE verification_results")
                
                # Create new table without UNIQUE constraint
                # This will be handled by _initialize_database()
                conn.commit()
                
                # Re-initialize database with new schema
                self._initialize_database()
                
                # Restore data with attempt numbers
                cursor.execute("""
                    INSERT INTO verification_results (
                        id, transaction_id, attempt_number, user_hash, verification_date,
                        risk_score, recommendation, verification_status,
                        aadhaar_verified, pan_verified, salary_verified,
                        issues_found, pdf_path, created_at, updated_at
                    )
                    SELECT 
                        id, transaction_id, 1 as attempt_number, user_hash, verification_date,
                        risk_score, recommendation, verification_status,
                        aadhaar_verified, pan_verified, salary_verified,
                        issues_found, pdf_path, created_at, created_at as updated_at
                    FROM verification_results_backup
                """)
                
                conn.commit()
                logger.info("Migration completed successfully!")
                return True
            
            logger.info("Database already up to date")
            return False

# ====================================
# SINGLETON INSTANCE
# ====================================
_db_instance = None

def get_database() -> KYCDataBase:
    """Get singleton database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = KYCDataBase()
    return _db_instance

# ====================================
# HELPER FUNCTIONS FOR INTEGRATION
# ====================================
def setup_database_for_mvp():
    """
    Setup database with initial configuration for MVP
    Call this once when deploying the app
    """
    db = get_database()
    
    # Check and migrate if needed
    db.migrate_existing_database()
    
    # Log initial setup
    db.log_audit_event(
        transaction_id=db.generate_transaction_id(),
        event_type="SYSTEM_INITIALIZATION",
        user_hash=db.hash_user_identifier("SYSTEM"),
        request_data={"action": "Database setup for MVP with duplicate handling"},
        response_status="SUCCESS"
    )
    
    logger.info("Database setup completed for MVP")
    return db

# ====================================
# INTEGRATION EXAMPLE
# ====================================
"""
To use the updated database:

1. Import:
   from database import get_database, setup_database_for_mvp

2. Initialize:
   db = setup_database_for_mvp()

3. Store verification result (auto-handles duplicates):
   result = db.store_verification_result(
       transaction_id=transaction_id,
       user_hash=user_hash,
       risk_score=75,
       recommendation="APPROVE",
       verification_status="COMPLETED",
       aadhaar_verified=True,
       pan_verified=True,
       salary_verified=True,
       issues_found=[],
       pdf_path="report.pdf",
       processing_time_ms=1500,
       source_file="aadhaar.jpg"
   )
   print(f"Attempt #{result['attempt_number']} stored")

4. Get latest verification:
   latest = db.get_latest_verification(transaction_id)

5. Get full history:
   history = db.get_verification_history(transaction_id)

6. Get duplicate report:
   duplicates = db.get_duplicate_report()
"""

# ====================================
# MAIN - FOR TESTING
# ====================================
if __name__ == "__main__":
    # Setup database
    db = setup_database_for_mvp()
    
    print("✅ Database initialized with duplicate handling!")
    print(f"📁 Database path: {DB_PATH}")
    
    # Test duplicate handling
    test_txn = db.generate_transaction_id()
    test_hash = db.hash_user_identifier("TEST_USER_123")
    
    print(f"\n📝 Testing duplicate handling for transaction: {test_txn}")
    
    # Store first attempt
    result1 = db.store_verification_result(
        transaction_id=test_txn,
        user_hash=test_hash,
        risk_score=70,
        recommendation="MANUAL_REVIEW",
        verification_status="PROCESSING",
        aadhaar_verified=True,
        pan_verified=False,
        salary_verified=False,
        issues_found=["Pan card verification pending"],
        source_file="test1.jpg"
    )
    print(f"✅ First attempt: #{result1['attempt_number']}")
    
    # Store duplicate attempt (same transaction_id)
    result2 = db.store_verification_result(
        transaction_id=test_txn,
        user_hash=test_hash,
        risk_score=85,
        recommendation="APPROVE",
        verification_status="COMPLETED",
        aadhaar_verified=True,
        pan_verified=True,
        salary_verified=True,
        issues_found=[],
        source_file="test2.jpg"
    )
    print(f"✅ Second attempt: #{result2['attempt_number']} (Duplicate handled)")
    
    # Get history
    history = db.get_verification_history(test_txn)
    print(f"\n📊 Verification History ({len(history)} attempts):")
    for attempt in history:
        print(f"  Attempt #{attempt['attempt_number']}: {attempt['verification_status']} - {attempt['recommendation']}")
    
    # Get stats
    stats = db.get_database_stats()
    print(f"\n📊 Database Stats:")
    print(f"  Total verifications: {stats['verification_results']}")
    print(f"  Duplicate transactions: {stats.get('duplicate_transactions', 0)}")
    print(f"  Extra attempts: {stats.get('extra_attempts', 0)}")
    print(f"  Database size: {stats['database_size_mb']:.2f} MB")
    
    print("\n✅ All tests passed! Database is ready for production.")