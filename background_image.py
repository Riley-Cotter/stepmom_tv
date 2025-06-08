import glob
import subprocess
import logging

# Setup logging (if not already set)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Find all JPG files in /media/usb/
jpg_files = glob.glob("/media/usb/*.jpg")

if jpg_files:
    try:
        # Display all JPG images using fbi on virtual terminal 2
        # -T 2: use tty2
        # -a: auto zoom
        # --noverbose: suppress output
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

