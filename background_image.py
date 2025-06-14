import glob
import subprocess
import logging
import time

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def wait_for_usb_mount(mount_path="/media/usb", timeout=30):
    start_time = time.time()
    logging.info(f"Waiting for USB mount at {mount_path}...")

    while True:
        try:
            with open("/proc/mounts", "r") as mounts:
                mounted = any(mount_path in line for line in mounts)
        except Exception as e:
            logging.error(f"Error checking mounts: {e}")
            mounted = False

        if mounted:
            logging.info("USB is mounted.")
            return True

        if time.time() - start_time > timeout:
            logging.error(f"ERROR: USB not mounted after {timeout} seconds.")
            return False

        time.sleep(1)

if __name__ == "__main__":
    if not wait_for_usb_mount():
        logging.error("USB mount failed, aborting image display.")
    else:
        jpg_files = glob.glob("/media/usb/*.jpg")
        if jpg_files:
            try:
                subprocess.run(
                    "sudo fbi -T 2 -a --noverbose /media/usb/*.jpg",
                    shell=True,
                    check=True,
                    text=True,
                    capture_output=True
                )
                logging.info("Displayed default image(s).")
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to display image: {e.stderr}")
        else:
            logging.warning("No JPG images found in /media/usb/. Skipping image display.")
