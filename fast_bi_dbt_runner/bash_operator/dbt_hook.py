from __future__ import print_function
import os
import signal
import subprocess
import json
import socket
import sys
from pathlib import Path
from filelock import FileLock
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from fast_bi_dbt_runner.bash_operator.datawarehouse_secrets import DataWarehouseSecretsManager

class DbtCliHook(BaseHook):
    """
    Simple wrapper around the dbt CLI.

    :param env: If set, passes the env variables to the subprocess handler
    :type env: dict
    :param profiles_dir: If set, passed as the `--profiles-dir` argument to the `dbt` command
    :type profiles_dir: str
    :param target: If set, passed as the `--target` argument to the `dbt` command
    :type dbt_project_dir: str
    :param dbt_project_dir: The directory to run the CLI in
    :type vars: str
    :param vars: If set, passed as the `--vars` argument to the `dbt` command
    :type vars: dict
    :param full_refresh: If `True`, will fully-refresh incremental models.
    :type full_refresh: bool
    :param models: If set, passed as the `--models` argument to the `dbt` command
    :type models: str
    :param warn_error: If `True`, treat warnings as errors.
    :type warn_error: bool
    :param exclude: If set, passed as the `--exclude` argument to the `dbt` command
    :type exclude: str
    :param select: If set, passed as the `--select` argument to the `dbt` command
    :type select: str
    :param selector: If set, passed as the `--selector` argument to the `dbt` command
    :type selector: str
    :param dbt_bin: The `dbt` CLI. Defaults to `dbt`, so assumes it's on your `PATH`
    :type dbt_bin: str
    :param output_encoding: Output encoding of bash command. Defaults to utf-8
    :type output_encoding: str
    :param verbose: The operator will log verbosely to the Airflow logs
    :type verbose: bool
    :param warehouse_type: The type of data warehouse to use (bigquery, snowflake, redshift, fabric)
    :type warehouse_type: str
    :param debug: If `True`, enables debug logging
    :type debug: bool
    """

    # Map for backward compatibility with DATA_WAREHOUSE_PLATFORM
    DWH_PLATFORM_MAP = {
        "1": "bigquery",
        "2": "snowflake",
        "3": "redshift",
        "4": "fabric"
    }

    def __init__(self,
                 env=None,
                 profiles_dir=None,
                 target=None,
                 dbt_project_dir=None,
                 vars=None,
                 full_refresh=False,
                 data=False,
                 schema=False,
                 models=None,
                 exclude=None,
                 select=None,
                 selector=None,
                 dbt_bin='dbt',
                 output_encoding='utf-8',
                 verbose=True,
                 warn_error=False,
                 git_branch=None,
                 warehouse_type=None,
                 debug=False):
        self.env = env or {}
        self.profiles_dir = profiles_dir
        self.dbt_project_dir = dbt_project_dir
        self.target = target
        self.vars = vars
        self.full_refresh = full_refresh
        self.data = data
        self.schema = schema
        self.models = models
        self.exclude = exclude
        self.select = select
        self.selector = selector
        self.dbt_bin = dbt_bin
        self.verbose = verbose
        self.warn_error = warn_error
        self.output_encoding = output_encoding
        self.git_branch = git_branch
        self.worker_id = socket.gethostname()
        self._debug = debug
        
        # Add debug logging
        self._log_debug(f"[Worker: {self.worker_id}] Initializing DbtCliHook")
        self._log_debug(f"[Worker: {self.worker_id}] Python path: {sys.path}")
        self._log_debug(f"[Worker: {self.worker_id}] Current directory: {os.getcwd()}")
        
        try:
            # Check if we're using the new secrets management system
            self._using_new_secrets = os.path.exists("/fastbi/secrets")
            self._log_debug(f"[Worker: {self.worker_id}] Using new secrets management: {self._using_new_secrets}")
            
            # Handle warehouse type with backward compatibility
            self.warehouse_type = self._determine_warehouse_type(warehouse_type)
            self._log_debug(f"[Worker: {self.worker_id}] Determined warehouse type: {self.warehouse_type}")
            
            if self._using_new_secrets:
                # Try importing the secrets manager
                self._log_debug(f"[Worker: {self.worker_id}] Successfully imported DataWarehouseSecretsManager")
                
                # Initialize secrets manager if warehouse type is determined
                if self.warehouse_type:
                    try:
                        self.secrets_manager = DataWarehouseSecretsManager(debug=self._debug)
                        self.secrets_manager.setup_secrets(self.warehouse_type)
                        self._log_debug(f"[Worker: {self.worker_id}] Successfully initialized secrets manager for {self.warehouse_type}")
                        
                        # Check what environment variables are available
                        env_vars = self.secrets_manager.get_env_vars()
                        self._log_debug(f"[Worker: {self.worker_id}] Available environment variables: {list(env_vars.keys())}")
                    except Exception as e:
                        self.log.error(f"[Worker: {self.worker_id}] Failed to initialize secrets manager: {str(e)}")
                        raise
                else:
                    self.log.warning(f"[Worker: {self.worker_id}] No warehouse type determined, skipping secrets manager initialization")
            else:
                self._log_debug(f"[Worker: {self.worker_id}] Using legacy secrets management (workload identity)")
                # For backward compatibility, we don't need to initialize secrets manager
                # The workload identity will handle authentication
                self.secrets_manager = None
        except ImportError as e:
            self.log.error(f"[Worker: {self.worker_id}] Failed to import DataWarehouseSecretsManager: {str(e)}")
            raise

    def _log_debug(self, message: str) -> None:
        """Log message only if debug is enabled"""
        if self._debug:
            self.log.info(message)

    def _log_info(self, message: str, *args) -> None:
        """Log message regardless of debug setting"""
        if args:
            self.log.info(message, *args)
        else:
            self.log.info(message)

    def _log_warning(self, message: str) -> None:
        """Log warning regardless of debug setting"""
        self.log.warning(message)

    def _log_error(self, message: str) -> None:
        """Log error regardless of debug setting"""
        self.log.error(message)

    def _determine_warehouse_type(self, warehouse_type: str = None) -> str:
        """
        Determine the warehouse type with backward compatibility.
        First checks warehouse_type parameter, then falls back to DATA_WAREHOUSE_PLATFORM.
        If neither is provided, defaults to "bigquery" for backward compatibility.
        """
        try:
            self._log_debug(f"[Worker: {self.worker_id}] Determining warehouse type from input: {warehouse_type}")
            
            # First try the direct warehouse_type parameter
            if warehouse_type:
                normalized = warehouse_type.lower()
                if normalized not in self.DWH_PLATFORM_MAP.values():
                    self._log_warning(f"[Worker: {self.worker_id}] Invalid warehouse_type parameter: {warehouse_type}")
                self._log_debug(f"[Worker: {self.worker_id}] Using warehouse type from parameter: {normalized}")
                return normalized
                
            # Then check for DATA_WAREHOUSE_PLATFORM in environment
            dwh_platform = os.environ.get("DATA_WAREHOUSE_PLATFORM")
            if dwh_platform:
                normalized = self.DWH_PLATFORM_MAP.get(str(dwh_platform).lower())
                if not normalized:
                    self._log_warning(f"[Worker: {self.worker_id}] Invalid DATA_WAREHOUSE_PLATFORM value: {dwh_platform}")
                self._log_debug(f"[Worker: {self.worker_id}] Using warehouse type from environment: {normalized}")
                return normalized
            
            # Default to bigquery for backward compatibility
            self._log_info(f"[Worker: {self.worker_id}] No warehouse type specified, defaulting to bigquery")
            return "bigquery"
        except Exception as e:
            self._log_error(f"[Worker: {self.worker_id}] Error determining warehouse type: {str(e)}")
            return "bigquery"  # Default to bigquery on error for backward compatibility

    def _check_packages_dir(self):
        """
        Check if dbt_packages directory exists and install if missing.
        Uses file locking to prevent concurrent installations.
        """
        exec_cwd = f'/opt/airflow/dbt/{self.dbt_project_dir}'
        packages_dir = os.path.join(exec_cwd, 'dbt_packages')
        lock_file = os.path.join(exec_cwd, '.dbt_deps_lock')
        packages_yml = os.path.join(exec_cwd, 'packages.yml')

        self._log_debug(f"[Worker: {self.worker_id}] Checking dbt packages in {packages_dir}")

        # Check if packages.yml exists and if dbt_packages directory exists or is empty
        if os.path.exists(packages_yml) and (not os.path.exists(packages_dir) or not os.listdir(packages_dir)):
            self._log_debug(f"[Worker: {self.worker_id}] packages.yml found and dbt_packages missing or empty, initiating installation")
            
            # Create lock file if doesn't exist
            Path(lock_file).touch(exist_ok=True)
            
            # Use file lock with timeout
            lock = FileLock(lock_file, timeout=300)
            
            try:
                with lock:
                    # Double-check after acquiring lock
                    if not os.path.exists(packages_dir) or not os.listdir(packages_dir):
                        # Prepare dbt deps command
                        deps_cmd = [self.dbt_bin, 'deps']
                        if self.profiles_dir is not None:
                            deps_cmd.extend(['--profiles-dir', self.profiles_dir])
                        if self.target is not None:
                            deps_cmd.extend(['--target', self.target])

                        # Handle test/e2e environments
                        if self.target in ['test', 'e2e', 'e2e_test']:
                            cmd_prefix = f"export GIT_BRANCH={self.git_branch} && "
                        else:
                            cmd_prefix = ""

                        wrapped_cmd = ['bash', '-c', f"{cmd_prefix}{' '.join(deps_cmd)}"]

                        if self.verbose:
                            self._log_debug(f"[Worker: {self.worker_id}] Running: {' '.join(wrapped_cmd)}")

                        # Use same subprocess approach as main command
                        sp = subprocess.Popen(
                            wrapped_cmd,
                            env=self.env if self.env or self.env == {} else os.environ,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            cwd=exec_cwd,
                            close_fds=True
                        )

                        # Handle output same way as main command
                        for line in iter(sp.stdout.readline, b''):
                            line = line.decode(self.output_encoding).rstrip()
                            self._log_info(f"[deps] {line}")
                        
                        sp.wait()

                        if sp.returncode:
                            raise AirflowException("dbt deps command failed")

                        self._log_debug(f"[Worker: {self.worker_id}] Successfully installed dbt packages")
                    
            except Exception as e:
                self._log_error(f"[Worker: {self.worker_id}] Error during package installation: {str(e)}")
                raise AirflowException(f"Failed to install dbt packages: {str(e)}")
        else:
            self._log_debug(f"[Worker: {self.worker_id}] dbt_packages directory exists and not empty, skipping installation")

    def _check_datawarehouse_connection(self):
        """
        Check data warehouse connection using dbt debug command.
        Only runs when debug mode is enabled.
        Uses file locking to prevent concurrent debug checks.
        """
        if not self._debug:
            self._log_debug(f"[Worker: {self.worker_id}] Debug mode not enabled, skipping connection check")
            return

        exec_cwd = f'/opt/airflow/dbt/{self.dbt_project_dir}'
        lock_file = os.path.join(exec_cwd, '.dbt_debug_lock')

        self._log_debug(f"[Worker: {self.worker_id}] Checking data warehouse connection")

        # Create lock file if doesn't exist
        Path(lock_file).touch(exist_ok=True)
        
        # Use file lock with timeout
        lock = FileLock(lock_file, timeout=300)
        
        try:
            with lock:
                # Prepare dbt debug command
                debug_cmd = [self.dbt_bin, 'debug']
                if self.profiles_dir is not None:
                    debug_cmd.extend(['--profiles-dir', self.profiles_dir])
                if self.target is not None:
                    debug_cmd.extend(['--target', self.target])

                # Initialize cmd_prefix with exports
                exports = []
                
                # Get warehouse environment variables first
                warehouse_env_vars = {}
                if hasattr(self, 'secrets_manager'):
                    warehouse_env_vars = self.secrets_manager.get_env_vars()
                    self._log_debug(f"[Worker: {self.worker_id}] Retrieved warehouse env vars: {list(warehouse_env_vars.keys())}")
                    
                    # Add warehouse environment variables
                    if warehouse_env_vars:
                        for key, value in warehouse_env_vars.items():
                            if value is not None:
                                # Escape single quotes in the value
                                escaped_value = str(value).replace("'", "'\\''")
                                exports.append(f"export {key}='{escaped_value}'")
                                self._log_debug(f"[Worker: {self.worker_id}] Added export for {key}")
                    else:
                        self._log_warning(f"[Worker: {self.worker_id}] No warehouse environment variables available")
                
                # Handle test/e2e environments - only add GIT_BRANCH for these targets
                if self.target in ['test', 'e2e', 'e2e_test']:
                    exports.append(f"export GIT_BRANCH={self.git_branch}")
                    self._log_debug(f"[Worker: {self.worker_id}] Added export for GIT_BRANCH")

                # Combine all exports with && between them
                cmd_prefix = ""
                if exports:
                    cmd_prefix = " && ".join(exports) + " && "
                    self._log_debug(f"[Worker: {self.worker_id}] Final exports count: {len(exports)}")

                wrapped_cmd = ['bash', '-c', f"{cmd_prefix}{' '.join(debug_cmd)}"]

                if self.verbose:
                    # Log the command but mask sensitive values
                    log_cmd = wrapped_cmd[:]
                    log_cmd[2] = log_cmd[2].replace(self.git_branch, "***") if self.git_branch else log_cmd[2]
                    if hasattr(self, 'secrets_manager') and warehouse_env_vars:
                        for key in warehouse_env_vars.keys():
                            if key in log_cmd[2]:
                                log_cmd[2] = log_cmd[2].replace(f"{key}='{warehouse_env_vars[key]}'", f"{key}='***'")
                    self._log_debug(f"[Worker: {self.worker_id}] Running command (with masked values): {' '.join(log_cmd)}")

                # Create environment dict for subprocess
                env = os.environ.copy()
                if self.env:
                    env.update(self.env)
                
                # Add warehouse environment variables to subprocess environment
                if hasattr(self, 'secrets_manager') and warehouse_env_vars:
                    self._log_debug(f"[Worker: {self.worker_id}] Adding to subprocess env: {list(warehouse_env_vars.keys())}")
                    env.update(warehouse_env_vars)

                # Use same subprocess approach as main command
                sp = subprocess.Popen(
                    wrapped_cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=exec_cwd,
                    close_fds=True
                )

                # Handle output same way as main command
                for line in iter(sp.stdout.readline, b''):
                    line = line.decode(self.output_encoding).rstrip()
                    self._log_info(f"[debug] {line}")
                
                sp.wait()

                if sp.returncode:
                    raise AirflowException("dbt debug command failed")

                self._log_debug(f"[Worker: {self.worker_id}] Successfully verified data warehouse connection")
                
        except Exception as e:
            self._log_error(f"[Worker: {self.worker_id}] Error during connection check: {str(e)}")
            raise AirflowException(f"Failed to verify data warehouse connection: {str(e)}")

    def _dump_vars(self):

        return f"'{json.dumps(self.vars)}'"

    def run_cli(self, *command):
        """
        Run the dbt cli

        :param command: The dbt command to run
        :type command: str
        """
        self._log_debug(f"[Worker: {self.worker_id}] Starting run_cli with command: {command}")
        
        # Check for dependencies before running any command
        self._check_packages_dir()
        
        # Refresh secrets and environment variables only if using new secrets management
        warehouse_env_vars = {}
        if self._using_new_secrets and hasattr(self, 'secrets_manager'):
            self._log_debug(f"[Worker: {self.worker_id}] Refreshing secrets for warehouse type: {self.warehouse_type}")
            self.secrets_manager.setup_secrets(self.warehouse_type)
            warehouse_env_vars = self.secrets_manager.get_env_vars()
            self._log_debug(f"[Worker: {self.worker_id}] Got warehouse env vars: {list(warehouse_env_vars.keys())}")
        else:
            self._log_debug(f"[Worker: {self.worker_id}] Using legacy secrets management (workload identity)")
        
        dbt_cmd = [self.dbt_bin, *command]

        if self.profiles_dir is not None:
            dbt_cmd.extend(['--profiles-dir', self.profiles_dir])

        if self.target is not None:
            dbt_cmd.extend(['--target', self.target])

        if self.vars is not None:
            dbt_cmd.extend(['--vars', self._dump_vars()])

        if self.data:
            dbt_cmd.extend(['--data'])

        if self.schema:
            dbt_cmd.extend(['--schema'])

        if self.models is not None:
            dbt_cmd.extend(['--models', self.models])

        if self.exclude is not None:
            dbt_cmd.extend(['--exclude', self.exclude])

        if self.select is not None:
            dbt_cmd.extend(['--select', self.select])

        if self.selector is not None:
            dbt_cmd.extend(['--selector', self.selector])

        if self.full_refresh:
            dbt_cmd.extend(['--full-refresh'])

        if self.warn_error:
            dbt_cmd.insert(1, '--warn-error')

        exec_cwd = f'/opt/airflow/dbt/{self.dbt_project_dir}'

        # Build environment exports
        exports = []
        
        # Add warehouse environment variables only if using new secrets management
        if self._using_new_secrets and warehouse_env_vars:
            for key, value in warehouse_env_vars.items():
                if value is not None:
                    # Escape single quotes in the value
                    escaped_value = str(value).replace("'", "'\\''")
                    exports.append(f"export {key}='{escaped_value}'")
                    self._log_debug(f"[Worker: {self.worker_id}] Adding export for {key}")
        
        # Then add GIT_BRANCH if needed
        if self.target in ['test', 'e2e', 'e2e_test']:
            exports.append(f"export GIT_BRANCH={self.git_branch}")
            self._log_debug(f"[Worker: {self.worker_id}] Adding export for GIT_BRANCH")

        # Build the command prefix
        cmd_prefix = ""
        if exports:
            cmd_prefix = " && ".join(exports) + " && "
            self._log_debug(f"[Worker: {self.worker_id}] Command prefix will include {len(exports)} exports")
        
        wrapped_cmd = ['bash', '-c', f"{cmd_prefix}{' '.join(dbt_cmd)}"]

        if self.verbose:
            # Log the command but mask sensitive values
            log_cmd = wrapped_cmd[:]
            log_cmd[2] = log_cmd[2].replace(self.git_branch, "***") if self.git_branch else log_cmd[2]
            if warehouse_env_vars:
                for key in warehouse_env_vars.keys():
                    if key in log_cmd[2]:
                        log_cmd[2] = log_cmd[2].replace(f"{key}='{warehouse_env_vars[key]}'", f"{key}='***'")
            self._log_info(f"[Worker: {self.worker_id}] Running command (with masked values): {' '.join(log_cmd)}")

        # Create environment dict for subprocess
        env = os.environ.copy()
        if self.env:
            env.update(self.env)
            self._log_debug(f"[Worker: {self.worker_id}] Added {len(self.env)} variables from self.env")
        
        # Add warehouse environment variables to subprocess environment only if using new secrets management
        if self._using_new_secrets and warehouse_env_vars:
            env.update(warehouse_env_vars)
            self._log_debug(f"[Worker: {self.worker_id}] Added {len(warehouse_env_vars)} warehouse variables to subprocess env")

        # Log final environment state
        if self.verbose:
            env_keys = set(env.keys())
            self._log_debug(f"[Worker: {self.worker_id}] Final subprocess environment will have {len(env_keys)} variables")
            if warehouse_env_vars:
                for key in warehouse_env_vars.keys():
                    if key in env:
                        self._log_debug(f"[Worker: {self.worker_id}] Environment will include {key}")
                    else:
                        self._log_warning(f"[Worker: {self.worker_id}] Environment is missing {key}")

        sp = subprocess.Popen(
            wrapped_cmd,
            env=env,  # Use the updated environment
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=exec_cwd,
            close_fds=True)

        self.sp = sp
        self._log_info("Output:")
        line = ''
        for line in iter(sp.stdout.readline, b''):
            line = line.decode(self.output_encoding).rstrip()
            self._log_info(line)
        sp.wait()
        self._log_info(
            "Command exited with return code %s",
            sp.returncode
        )

        if sp.returncode:
            raise AirflowException("dbt command failed")

    def on_kill(self):
        self._log_info('Sending SIGTERM signal to dbt command')
        os.killpg(os.getpgid(self.sp.pid), signal.SIGTERM)