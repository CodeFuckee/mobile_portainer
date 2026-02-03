import os
import git
import time
import logging
import sys
import subprocess
from urllib.parse import urlparse, quote
from app.core.config import (
    GIT_AUTO_UPDATE, GIT_REPO_URL, GIT_BRANCH, 
    GIT_CHECK_INTERVAL, GIT_USER, GIT_PASSWORD, GIT_SSL_NO_VERIFY
)

logger = logging.getLogger(__name__)

def git_auto_updater():
    """
    Background thread to check for git updates and pull them.
    """
    if not GIT_AUTO_UPDATE or not GIT_REPO_URL:
        logger.info("Git auto update disabled or no repo URL provided.")
        return

    # Construct Authenticated URL if credentials provided
    final_repo_url = GIT_REPO_URL
    if GIT_USER and GIT_PASSWORD:
        try:
            parsed = urlparse(GIT_REPO_URL)
            user_encoded = quote(GIT_USER, safe='')
            pass_encoded = quote(GIT_PASSWORD, safe='')
            # Reconstruct netloc with auth
            netloc = f"{user_encoded}:{pass_encoded}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            final_repo_url = parsed._replace(netloc=netloc).geturl()
        except Exception as e:
             logger.error(f"Failed to construct authenticated URL: {e}")
             return

    logger.info(f"Starting Git auto updater (Repo: {GIT_REPO_URL}, Branch: {GIT_BRANCH})")
    
    repo_dir = os.getcwd()
    try:
        # Check if current directory is a git repo
        try:
            repo = git.Repo(repo_dir)
            # Update remote URL if needed (e.g. auth changed)
            try:
                repo.remotes.origin.set_url(final_repo_url)
            except Exception:
                pass
        except git.exc.InvalidGitRepositoryError:
            logger.info("Current directory is not a git repository. Initializing...")
            # Initialize git repo
            repo = git.Repo.init(repo_dir)
            repo.create_remote('origin', final_repo_url)
        
        # Configure SSL Verify
        if GIT_SSL_NO_VERIFY:
            with repo.config_writer() as writer:
                writer.set_value("http", "sslVerify", "false")

        # Initial fetch
        try:
            repo.git.fetch()
            # Reset hard to remote branch (Warning: Overwrites local files!)
            try:
                repo.git.reset('--hard', f'origin/{GIT_BRANCH}')
            except git.GitCommandError as e:
                if "untracked working tree files would be overwritten" in str(e) or "Please move or remove them" in str(e):
                    logger.warning("Untracked files detected. Forcing checkout...")
                    repo.git.checkout('-B', GIT_BRANCH, f'origin/{GIT_BRANCH}', force=True)
                else:
                    raise e
            
            logger.info(f"Successfully initialized and synced with {GIT_BRANCH}")
            
            # Initial check for dependencies (optional, but good for first run)
            # subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            
        except Exception as e:
                logger.error(f"Initial sync failed: {e}")

        while True:
            try:
                # Fetch remote
                repo.remotes.origin.fetch()
                
                # Check for changes
                local_commit = repo.head.commit
                remote_commit = repo.commit(f'origin/{GIT_BRANCH}')

                if local_commit != remote_commit:
                    logger.info("Found updates. Pulling...")
                    
                    # Check if requirements.txt changed
                    requirements_changed = False
                    try:
                        diffs = local_commit.diff(remote_commit)
                        for diff in diffs:
                            if diff.a_path == 'requirements.txt' or diff.b_path == 'requirements.txt':
                                requirements_changed = True
                                break
                    except Exception as e:
                        logger.warning(f"Failed to check for requirements.txt changes: {e}")

                    # Pull changes
                    try:
                        repo.git.pull('origin', GIT_BRANCH)
                    except git.GitCommandError as e:
                        if "untracked working tree files would be overwritten" in str(e) or "Please move or remove them" in str(e):
                             logger.warning("Conflict detected during pull. Forcing checkout...")
                             repo.git.fetch()
                             repo.git.checkout('-B', GIT_BRANCH, f'origin/{GIT_BRANCH}', force=True)
                        else:
                             raise e
                    
                    logger.info("Update successful. Server should reload if running with --reload.")
                    
                    # Install dependencies if needed
                    if requirements_changed:
                        logger.info("requirements.txt changed. Installing new dependencies...")
                        try:
                            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
                            logger.info("Dependencies installed successfully.")
                        except subprocess.CalledProcessError as e:
                            logger.error(f"Failed to install dependencies: {e}")
                
            except Exception as e:
                logger.error(f"Error in git auto updater: {e}")
            
            time.sleep(GIT_CHECK_INTERVAL)
            
    except Exception as e:
        logger.error(f"Fatal error in git auto updater: {e}")
