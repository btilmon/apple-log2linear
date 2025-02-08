import os
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
import av
import numpy as np
import cv2
import shutil
import argparse

def apple_log_decode(P):
    """
    Decode Apple Log-encoded pixel values into linear reflectance R.
    P can be a scalar or NumPy array (float32 or float64).

    Parameters from the Apple Log White Paper:
      R0     = -0.05641088
      RI     =  0.01
      c      = 47.28711236
      beta   = 0.00964052
      gamma  = 0.08550479
      delta  = 0.69336945
    """
    R0     = -0.05641088
    RI     =  0.01
    c      = 47.28711236
    beta   = 0.00964052
    gamma  = 0.08550479
    delta  = 0.69336945

    PI = c * (RI - R0)**2

    R = np.where(
        P < 0,
        R0,
        np.where(
            P < PI,
            np.sqrt(P / c) + R0,
            np.power(2.0, (P - delta) / gamma) - beta
        )
    )
    
    return R

def process_apple_log_video(base_dir, mov_filename, step):
    """
    Process the given Apple Log MOV file, decode it to linear,
    and save both 16-bit linear PNGs and gamma-corrected 8-bit PNGs for COLMAP.

    base_dir    : The base directory to place the 'tmp/images-16bit' and
                  'tmp/images-8bit' folders.
    mov_filename: The name of the .mov file (including extension).
    step  : The number of frames to skip between saved frames.
    """

    # Construct paths
    tmp_dir = os.path.join(base_dir, 'tmp')
    images_32bit_dir = os.path.join(tmp_dir, 'images-32bit')
    images_16bit_dir = os.path.join(tmp_dir, 'images-16bit')
    images_8bit_dir  = os.path.join(tmp_dir, 'images')

    # Delete directories if they exist
    if os.path.exists(images_16bit_dir):
        shutil.rmtree(images_16bit_dir)
    if os.path.exists(images_8bit_dir):
        shutil.rmtree(images_8bit_dir)
    if os.path.exists(images_32bit_dir):
        shutil.rmtree(images_32bit_dir)

    # Create directories
    os.makedirs(images_16bit_dir, exist_ok=True)
    os.makedirs(images_8bit_dir,  exist_ok=True)
    os.makedirs(images_32bit_dir,  exist_ok=True)

    # Open the MOV container
    mov_path = os.path.join(base_dir, mov_filename)
    container = av.open(mov_path)

    global_frame_index = 0
    frame_index = 0
    for packet in container.demux():
        # Only process packets from the video stream
        if packet.stream.type == 'video':
            for frame in packet.decode():

                if global_frame_index % step == 0:
                    # Reformat to RGB48LE (16-bit)
                    rgb_frame = frame.reformat(format='rgb48le')
                    arr = rgb_frame.to_ndarray()  # (H, W, 3), dtype=uint16

                    # Convert to float range [0,1]
                    arr_float = arr.astype(np.float32) / 65535.0
                    # Apple Log decode to linear
                    arr_lin = apple_log_decode(arr_float)
                    
                    # save unclipped 32 bit linear exr with opencv
                    out_exr_path = os.path.join(images_32bit_dir,
                                                f'{frame_index:06d}.exr')
                    cv2.imwrite(out_exr_path, arr_lin[:, :, ::-1])

                    # save 16-bit linear
                    # scale back up to [0,65535]
                    arr_lin_16 = (np.clip(arr_lin, 0.0, 1.0) * 65535.0).astype(np.uint16)
                    # OpenCV uses BGR order, so flip color channels
                    out_16bit_path = os.path.join(images_16bit_dir,
                                                f'{frame_index:06d}.png')
                    cv2.imwrite(out_16bit_path, arr_lin_16[:, :, ::-1])

                    # save 8-bit gamma-corrected 
                    gamma = 2.2
                    arr_lin_gamma = np.power(np.clip(arr_lin, 0.0, 1.0), 1.0 / gamma)
                    arr_lin_8 = (arr_lin_gamma * 255.0).astype(np.uint8)
                    out_8bit_path = os.path.join(images_8bit_dir,
                                                f'{frame_index:06d}.png')
                    cv2.imwrite(out_8bit_path, arr_lin_8[:, :, ::-1])

                    frame_index += 1

                global_frame_index += 1

    print(f"Finished processing {frame_index} frames.")
    print(f"32-bit frames in: {images_32bit_dir}")
    print(f"16-bit frames in: {images_16bit_dir}")
    print(f"8-bit frames in:  {images_8bit_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process an Apple Log-encoded .mov video')
    parser.add_argument('--base_directory', type=str, help='Base directory to create output folders')
    parser.add_argument('--mov_file', type=str, help='Name of the .mov file (including extension)')
    parser.add_argument('--step', type=int, default=5, help='Video temporal downsampling factor')
    args = parser.parse_args() 
    process_apple_log_video(args.base_directory, args.mov_file, args.step)

