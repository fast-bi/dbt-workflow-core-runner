import os
import threading
import base64
import logging
from pathlib import Path
from typing import Optional, Dict
from filelock import FileLock

class DataWarehouseSecretsManager:
    """
    Thread-safe manager for handling data warehouse secrets.
    Uses file locking to prevent concurrent access issues.
    """
    
    _instance = None
    _lock = threading.Lock()
    _setup_logged = False  # Track if we've already logged setup messages
    
    # Map for both numeric and string warehouse types
    WAREHOUSE_TYPE_MAP = {
        "1": "bigquery",
        "2": "snowflake",
        "3": "redshift",
        "4": "fabric",
        "bigquery": "bigquery",
        "snowflake": "snowflake",
        "redshift": "redshift",
        "fabric": "fabric"
    }
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DataWarehouseSecretsManager, cls).__new__(cls)
                    # Store the debug flag for initialization
                    cls._instance._debug_flag = kwargs.get('debug', False)
        return cls._instance
    
    def __init__(self, debug=False):
        # Skip initialization if already initialized
        if hasattr(self, '_initialized'):
            # Update debug flag if it's different
            if self._debug != debug:
                self._debug = debug
            return
            
        self.logger = logging.getLogger(__name__)
        self.secrets_base_path = "/fastbi/secrets"
        self.secrets_ready_file = Path("/tmp/secrets_ready")
        # Use home directory for snowsql secrets
        self.snowsql_base_path = "/snowsql"
        # Store environment variables that need to be passed to child processes
        self._env_vars = {}
        # Store warehouse-specific environment variables
        self._warehouse_env_vars = {
            "snowflake": {
                "SNOWSQL_PRIVATE_KEY_PASSPHRASE": None,
                "SNOWFLAKE_PRIVATE_KEY_PATH": None
            },
            "bigquery": {
                "GOOGLE_APPLICATION_CREDENTIALS": None
            },
            "redshift": {
                "REDSHIFT_PASSWORD": None,
                "REDSHIFT_USER": None,
                "REDSHIFT_HOST": None,
                "REDSHIFT_PORT": None
            },
            "fabric": {
                "FABRIC_USER": None,
                "FABRIC_PASSWORD": None,
                "FABRIC_SERVER": None,
                "FABRIC_DATABASE": None,
                "FABRIC_PORT": None,
                "FABRIC_AUTHENTICATION": None
            }
        }
        self._current_warehouse_type = None
        self._debug = getattr(self, '_debug_flag', debug)
        self._initialized = True
    
    def _log_debug(self, message: str) -> None:
        """Log message only if debug is enabled"""
        if self._debug:
            self.logger.info(message)

    def _log_info(self, message: str) -> None:
        """Log message regardless of debug setting"""
        self.logger.info(message)

    def _log_warning(self, message: str) -> None:
        """Log warning regardless of debug setting"""
        self.logger.warning(message)

    def _log_error(self, message: str) -> None:
        """Log error regardless of debug setting"""
        self.logger.error(message)
    
    def _are_secrets_ready(self) -> bool:
        """Check if secrets are ready by looking for the ready file"""
        return self.secrets_ready_file.exists()
    
    def _mark_secrets_ready(self) -> None:
        """Mark secrets as ready by creating the ready file"""
        self.secrets_ready_file.touch()
    
    def _normalize_warehouse_type(self, warehouse_type: str) -> str:
        """Normalize warehouse type to standard string format"""
        if not warehouse_type:
            return None
        try:
            normalized = self.WAREHOUSE_TYPE_MAP.get(str(warehouse_type).lower())
            if not normalized:
                self._log_warning(f"Invalid warehouse type provided: {warehouse_type}")
            return normalized
        except Exception as e:
            self._log_error(f"Error normalizing warehouse type: {str(e)}")
            return None
    
    def _read_secret(self, secret_path: str) -> str:
        """Safely read a secret file"""
        try:
            with open(secret_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            self._log_error(f"Failed to read secret from {secret_path}: {str(e)}")
            raise
    
    def _setup_bigquery(self) -> None:
        """Configure BigQuery secrets"""
        try:
            if not self._setup_logged:
                self._log_debug("Setting up BigQuery secrets")
            
            # Create secret directory if it doesn't exist
            secret_dir = Path("/bigquery/secret")
            sa_json_path = secret_dir / "sa.json"
            
            # Only create and write sa.json if it doesn't exist
            if not sa_json_path.exists():
                secret_dir.mkdir(exist_ok=True)
                
                # Handle service account key
                sa_key_path = Path(self.secrets_base_path) / "bigquery" / "DBT_DEPLOY_GCP_SA_SECRET"
                if sa_key_path.exists():
                    # Store lock file in the writable bigquery directory
                    lock_path = Path("/bigquery") / "DBT_DEPLOY_GCP_SA_SECRET.lock"
                    with FileLock(str(lock_path)):
                        # Read and decode base64 service account key
                        decoded_key = base64.b64decode(self._read_secret(str(sa_key_path)))
                        # Write to sa.json
                        with open(sa_json_path, "wb") as f:
                            f.write(decoded_key)
                else:
                    raise ValueError("BigQuery service account secret not found")
            
            # Store environment variable
            self._warehouse_env_vars["bigquery"]["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_json_path)
            if not self._setup_logged:
                self._log_debug("Successfully set up BigQuery secrets")
            
        except Exception as e:
            self._log_error(f"Failed to setup BigQuery secrets: {str(e)}")
            raise
    
    def _setup_snowflake(self) -> None:
        """Configure Snowflake secrets"""
        try:
            self._log_debug("Setting up Snowflake secrets")
            
            # Check if secrets are already prepared
            snowsql_dir = Path(self.snowsql_base_path) / "secrets"
            key_path = snowsql_dir / "rsa_key.p8"
            
            # If key file doesn't exist, prepare it
            if not key_path.exists():
                self._log_debug("Preparing Snowflake secrets - RSA key not found, creating it")
                # Create directories if they don't exist
                snowsql_dir.mkdir(parents=True, exist_ok=True)
                
                # Get private key from source
                secret_key_path = Path(self.secrets_base_path) / "snowflake" / "SNOWFLAKE_PRIVATE_KEY"
                if not secret_key_path.exists():
                    self._log_warning(f"Snowflake private key secret not found at path: {secret_key_path}")
                    # Instead of raising an error, set a default empty key
                    self._log_warning("Using default empty key for Snowflake")
                    with open(key_path, "w") as f:
                        f.write("")
                    os.chmod(key_path, 0o600)
                else:
                    # Copy private key to target location
                    with open(key_path, "w") as f:
                        f.write(self._read_secret(str(secret_key_path)))
                    os.chmod(key_path, 0o600)
                    self._log_debug(f"Successfully created RSA key at {key_path}")
            else:
                self._log_debug(f"RSA key already exists at {key_path}")
            
            # Set passphrase environment variable
            passphrase_path = Path(self.secrets_base_path) / "snowflake" / "SNOWFLAKE_PASSPHRASE"
            if not passphrase_path.exists():
                self._log_warning(f"Snowflake passphrase secret not found at path: {passphrase_path}")
                # Use empty passphrase as fallback
                passphrase = ""
            else:
                # Read passphrase
                passphrase = self._read_secret(str(passphrase_path))
                self._log_debug("Read passphrase from secret file")
            
            # Initialize snowflake env vars if not already initialized
            if "snowflake" not in self._warehouse_env_vars:
                self._warehouse_env_vars["snowflake"] = {}
            
            # Set the environment variables
            self._warehouse_env_vars["snowflake"]["SNOWSQL_PRIVATE_KEY_PASSPHRASE"] = passphrase
            self._warehouse_env_vars["snowflake"]["SNOWFLAKE_PRIVATE_KEY_PATH"] = str(key_path)
            
            self._log_debug("Environment variables set:")
            for key, value in self._warehouse_env_vars["snowflake"].items():
                if value:
                    self._log_debug(f"  - {key}: [value is set]")
                else:
                    self._log_warning(f"  - {key}: [not set]")
            
            self._log_debug("Successfully set up Snowflake secrets")
            
        except Exception as e:
            self._log_error(f"Failed to setup Snowflake secrets: {str(e)}")
            # Instead of raising the error, log it and continue
            self._log_warning("Continuing with default Snowflake configuration")
    
    def _setup_redshift(self) -> None:
        """Configure Redshift secrets"""
        try:
            if not self._setup_logged:
                self._log_debug("Setting up Redshift secrets")
            
            # Create a writable directory for Redshift secrets
            redshift_dir = Path("/redshift") / "secrets"
            redshift_dir.mkdir(parents=True, exist_ok=True)
            
            required_vars = ["REDSHIFT_PASSWORD", "REDSHIFT_USER", "REDSHIFT_HOST", "REDSHIFT_PORT"]
            missing_vars = []
            
            for var in required_vars:
                secret_path = Path(self.secrets_base_path) / "redshift" / var
                if secret_path.exists():
                    # Store lock file in the writable redshift directory
                    lock_path = redshift_dir / f"{var}.lock"
                    with FileLock(str(lock_path)):
                        value = self._read_secret(str(secret_path))
                        self._warehouse_env_vars["redshift"][var] = value
                else:
                    missing_vars.append(var)
                    
            if missing_vars:
                raise ValueError(f"Missing required Redshift secrets: {', '.join(missing_vars)}")
            
            if not self._setup_logged:
                self._log_debug("Successfully set up Redshift secrets")
            
        except Exception as e:
            self._log_error(f"Failed to setup Redshift secrets: {str(e)}")
            raise
    
    def _setup_fabric(self) -> None:
        """Configure Fabric secrets"""
        try:
            if not self._setup_logged:
                self._log_debug("Setting up Fabric secrets")
            
            # Create a writable directory for Fabric secrets
            fabric_dir = Path("/fabric") / "secrets"
            fabric_dir.mkdir(parents=True, exist_ok=True)
            
            required_vars = ["FABRIC_USER", "FABRIC_PASSWORD", "FABRIC_SERVER", 
                           "FABRIC_DATABASE", "FABRIC_PORT", "FABRIC_AUTHENTICATION"]
            missing_vars = []
            
            for var in required_vars:
                secret_path = Path(self.secrets_base_path) / "fabric" / var
                if secret_path.exists():
                    # Store lock file in the writable fabric directory
                    lock_path = fabric_dir / f"{var}.lock"
                    with FileLock(str(lock_path)):
                        value = self._read_secret(str(secret_path))
                        self._warehouse_env_vars["fabric"][var] = value
                else:
                    missing_vars.append(var)
                    
            if missing_vars:
                raise ValueError(f"Missing required Fabric secrets: {', '.join(missing_vars)}")
            
            if not self._setup_logged:
                self._log_debug("Successfully set up Fabric secrets")
            
        except Exception as e:
            self._log_error(f"Failed to setup Fabric secrets: {str(e)}")
            raise
    
    def setup_secrets(self, warehouse_type: str) -> None:
        """
        Set up secrets for the specified warehouse type.
        This only handles the file-based secrets setup.
        """
        self._log_debug(f"Setting up secrets for warehouse type: {warehouse_type}")
        
        # Normalize warehouse type
        warehouse_type = self._normalize_warehouse_type(warehouse_type)
        if not warehouse_type:
            raise ValueError(f"Invalid warehouse type: {warehouse_type}")

        # Get the appropriate setup function
        setup_functions = {
            'bigquery': self._setup_bigquery,
            'snowflake': self._setup_snowflake,
            'redshift': self._setup_redshift,
            'fabric': self._setup_fabric
        }

        setup_func = setup_functions.get(warehouse_type.lower())
        if not setup_func:
            raise ValueError(f"Unsupported warehouse type: {warehouse_type}")

        # If secrets are already set up for this warehouse type, skip
        if self._are_secrets_ready() and self._current_warehouse_type == warehouse_type:
            self._log_debug("Secrets files already set up, skipping")
            return

        # Call the setup function
        setup_func()
        
        # Update current warehouse type
        self._current_warehouse_type = warehouse_type
        self._mark_secrets_ready()

    def _setup_snowflake_secrets(self) -> None:
        """Configure Snowflake secret files"""
        try:
            # Check if secrets are already prepared
            snowsql_dir = Path(self.snowsql_base_path) / "secrets"
            key_path = snowsql_dir / "rsa_key.p8"
            
            # If key file doesn't exist, prepare it
            if not key_path.exists():
                self._log_debug("Preparing Snowflake secrets - RSA key not found, creating it")
                # Create directories if they don't exist
                snowsql_dir.mkdir(parents=True, exist_ok=True)
                
                # Get private key from source
                secret_key_path = Path(self.secrets_base_path) / "snowflake" / "SNOWFLAKE_PRIVATE_KEY"
                if not secret_key_path.exists():
                    self._log_error("Snowflake private key secret not found at path: " + str(secret_key_path))
                    raise ValueError("Snowflake private key secret not found")
                
                # Copy private key to target location
                with open(key_path, "w") as f:
                    f.write(self._read_secret(str(secret_key_path)))
                os.chmod(key_path, 0o600)
                self._log_debug(f"Successfully created RSA key at {key_path}")
            else:
                self._log_debug(f"RSA key already exists at {key_path}")
            
            self._log_debug("Successfully set up Snowflake secret files")
            
        except Exception as e:
            self._log_error(f"Failed to setup Snowflake secrets: {str(e)}")
            raise

    def _setup_bigquery_secrets(self) -> None:
        """Configure BigQuery secret files"""
        try:
            # Create secret directory if it doesn't exist
            secret_dir = Path("/bigquery/secret")
            sa_json_path = secret_dir / "sa.json"
            
            # Only create and write sa.json if it doesn't exist
            if not sa_json_path.exists():
                self._log_debug("Preparing BigQuery secrets - service account JSON not found, creating it")
                secret_dir.mkdir(exist_ok=True)
                
                # Handle service account key
                sa_key_path = Path(self.secrets_base_path) / "bigquery" / "DBT_DEPLOY_GCP_SA_SECRET"
                if not sa_key_path.exists():
                    self._log_error("BigQuery service account secret not found at path: " + str(sa_key_path))
                    raise ValueError("BigQuery service account secret not found")
                
                # Read and decode base64 service account key
                decoded_key = base64.b64decode(self._read_secret(str(sa_key_path)))
                
                # Write to sa.json
                with open(sa_json_path, "wb") as f:
                    f.write(decoded_key)
                os.chmod(sa_json_path, 0o600)
                self._log_debug(f"Successfully created service account JSON at {sa_json_path}")
            else:
                self._log_debug(f"Service account JSON already exists at {sa_json_path}")
            
            self._log_debug("Successfully set up BigQuery secret files")
            
        except Exception as e:
            self._log_error(f"Failed to setup BigQuery secrets: {str(e)}")
            raise

    def get_env_vars(self) -> Dict[str, str]:
        """
        Get environment variables for the current warehouse type.
        This should be called every time we need environment variables.
        """
        if not self._current_warehouse_type:
            self._log_warning("No warehouse type set, returning empty dict")
            return {}
            
        self._log_debug(f"Getting environment variables for warehouse type: {self._current_warehouse_type}")
        
        # Get the appropriate environment variables
        if self._current_warehouse_type == 'snowflake':
            # Get passphrase environment variable
            passphrase_path = Path(self.secrets_base_path) / "snowflake" / "SNOWFLAKE_PASSPHRASE"
            if not passphrase_path.exists():
                self._log_warning(f"Snowflake passphrase secret not found at path: {passphrase_path}")
                passphrase = ""  # Use empty passphrase as fallback
            else:
                # Read passphrase
                passphrase = self._read_secret(str(passphrase_path))
                self._log_debug("Read passphrase from secret file")
            
            # Get key path
            key_path = Path(self.snowsql_base_path) / "secrets" / "rsa_key.p8"
            
            env_vars = {
                'SNOWSQL_PRIVATE_KEY_PASSPHRASE': passphrase,
                'SNOWFLAKE_PRIVATE_KEY_PATH': str(key_path)
            }
            
            # Log which variables are set
            for key, value in env_vars.items():
                if value:
                    self._log_debug(f"Environment variable {key} is set")
                else:
                    self._log_warning(f"Environment variable {key} is NOT set")
                    
            return env_vars
            
        elif self._current_warehouse_type == 'bigquery':
            # Check if service account JSON exists
            sa_json_path = Path("/bigquery/secret/sa.json")
            if not sa_json_path.exists():
                self._log_warning(f"BigQuery service account JSON not found at {sa_json_path}")
                return {}
                
            env_vars = {
                'GOOGLE_APPLICATION_CREDENTIALS': str(sa_json_path)
            }
            
            # Log which variables are set
            for key, value in env_vars.items():
                if value:
                    self._log_debug(f"Environment variable {key} is set to {value}")
                else:
                    self._log_warning(f"Environment variable {key} is NOT set")
                    
            return env_vars
            
        elif self._current_warehouse_type == 'redshift':
            env_vars = {}
            for var in ["REDSHIFT_PASSWORD", "REDSHIFT_USER", "REDSHIFT_HOST", "REDSHIFT_PORT"]:
                secret_path = Path(self.secrets_base_path) / "redshift" / var
                if secret_path.exists():
                    env_vars[var] = self._read_secret(str(secret_path))
                    self._log_debug(f"Read {var} from {secret_path}")
                else:
                    self._log_warning(f"Secret not found at {secret_path}")
            return env_vars
            
        elif self._current_warehouse_type == 'fabric':
            env_vars = {}
            for var in ["FABRIC_USER", "FABRIC_PASSWORD", "FABRIC_SERVER", 
                       "FABRIC_DATABASE", "FABRIC_PORT", "FABRIC_AUTHENTICATION"]:
                secret_path = Path(self.secrets_base_path) / "fabric" / var
                if secret_path.exists():
                    env_vars[var] = self._read_secret(str(secret_path))
                    self._log_debug(f"Read {var} from {secret_path}")
                else:
                    self._log_warning(f"Secret not found at {secret_path}")
            return env_vars
            
        self._log_warning(f"No environment variables found for warehouse type: {self._current_warehouse_type}")
        return {} 