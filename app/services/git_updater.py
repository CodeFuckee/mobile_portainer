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

def _construct_auth_url(base_url):
    """
    Construct URL with credentials if present.
    """
    if not GIT_USER or not GIT_PASSWORD:
        return base_url
        
    try:
        parsed = urlparse(base_url)
        user_encoded = quote(GIT_USER, safe='')
        pass_encoded = quote(GIT_PASSWORD, safe='')
        # Reconstruct netloc with auth
        netloc = f"{user_encoded}:{pass_encoded}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return parsed._replace(netloc=netloc).geturl()
    except Exception as e:
        logger.error(f"Failed to construct authenticated URL: {e}")
        return base_url

def _get_mirror_urls(primary_url):
    """
    Generate a list of URLs to try (Primary + Mirrors).
    Currently supports github.com -> githubfast.com
    """
    urls = [primary_url]
    
    # Add githubfast.com mirror if primary is github.com
    if "github.com" in primary_url:
        mirror_url = primary_url.replace("github.com", "githubfast.com")
        urls.append(mirror_url)
        
    return urls

def git_auto_updater():
    """
    Background thread to check for git updates and pull them.
    """
    if not GIT_AUTO_UPDATE or not GIT_REPO_URL:
        logger.info("Git auto update disabled or no repo URL provided.")
        return

    logger.info(f"Starting Git auto updater (Repo: {GIT_REPO_URL}, Branch: {GIT_BRANCH})")
    
    repo_dir = os.getcwd()
    
    # 1. Initialize Repo if needed
    try:
        try:
            repo = git.Repo(repo_dir)
        except git.exc.InvalidGitRepositoryError:
            logger.info("Current directory is not a git repository. Initializing...")
            repo = git.Repo.init(repo_dir)
            
            # Create remote with primary URL initially
            final_repo_url = _construct_auth_url(GIT_REPO_URL)
            repo.create_remote('origin', final_repo_url)
            
            # Immediately try to sync to avoid "ambiguous HEAD" state
            try:
                logger.info("Performing initial sync...")
                # Try fetching from configured URLs
                base_urls = _get_mirror_urls(GIT_REPO_URL)
                fetched = False
                
                for base_url in base_urls:
                    try:
                        url = _construct_auth_url(base_url)
                        repo.remotes.origin.set_url(url)
                        repo.git.fetch('origin')
                        fetched = True
                        break
                    except Exception:
                        continue
                
                if fetched:
                    # Reset hard to remote branch
                    repo.git.reset('--hard', f'origin/{GIT_BRANCH}')
                    # Set upstream tracking so 'git pull' works manually
                    try:
                        repo.git.branch('--set-upstream-to', f'origin/{GIT_BRANCH}', GIT_BRANCH)
                    except Exception:
                        # If branch doesn't exist locally yet (it should after reset), create it
                        try:
                            repo.git.checkout('-b', GIT_BRANCH, f'origin/{GIT_BRANCH}')
                        except Exception:
                            pass
                            
                    logger.info("Initial sync successful. Repository is now consistent with remote.")
                else:
                    logger.warning("Initial sync failed. Repository is empty.")
                    
            except Exception as e:
                logger.error(f"Error during initial sync: {e}")
            
        # Configure SSL Verify
        if GIT_SSL_NO_VERIFY:
            with repo.config_writer() as writer:
                writer.set_value("http", "sslVerify", "false")
                
    except Exception as e:
        logger.error(f"Fatal error initializing git repo: {e}")
        return

    while True:
        try:
            # 2. Try Fetching from available URLs
            base_urls = _get_mirror_urls(GIT_REPO_URL)
            fetch_success = False
            
            for base_url in base_urls:
                final_url = _construct_auth_url(base_url)
                logger.debug(f"Attempting to fetch from: {base_url}")
                
                try:
                    # Update remote URL
                    if 'origin' in repo.remotes:
                        repo.remotes.origin.set_url(final_url)
                    else:
                        repo.create_remote('origin', final_url)
                        
                    # Fetch
                    repo.git.fetch('origin')
                    fetch_success = True
                    logger.info(f"Successfully fetched from {base_url}")
                    break # Stop if successful
                except Exception as e:
                    logger.warning(f"Failed to fetch from {base_url}: {e}")
                    continue
            
            if not fetch_success:
                logger.error("Failed to fetch from all configured remotes.")
            else:
                # 3. Check for updates and Reset
                try:
                    local_commit = repo.head.commit
                    remote_ref = f'origin/{GIT_BRANCH}'
                    remote_commit = repo.commit(remote_ref)

                    if local_commit != remote_commit:
                        logger.info(f"Found updates ({local_commit.hexsha[:7]} -> {remote_commit.hexsha[:7]}). Updating...")
                        
                        # Check if requirements.txt changed
                        requirements_changed = False
                        try:
                            diffs = local_commit.diff(remote_commit)
                            for diff in diffs:
                                if diff.a_path == 'requirements.txt' or diff.b_path == 'requirements.txt':
                                    requirements_changed = True
                                    break
                        except Exception:
                            pass

                        # Reset hard to remote (Force sync)
                        # This avoids "no tracking information" and merge conflicts
                        repo.git.reset('--hard', remote_ref)
                        logger.info("Update successful (Hard Reset). Server should reload if running with --reload.")
                        
                        # Install dependencies if needed
                        if requirements_changed:
                            logger.info("requirements.txt changed. Installing new dependencies...")
                            try:
                                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
                                logger.info("Dependencies installed successfully.")
                            except subprocess.CalledProcessError as e:
                                logger.error(f"Failed to install dependencies: {e}")
                    else:
                        logger.debug("No updates found.")
                        
                except Exception as e:
                    logger.error(f"Error applying updates: {e}")

        except Exception as e:
            logger.error(f"Error in git auto updater loop: {e}")
        
        time.sleep(GIT_CHECK_INTERVAL)
