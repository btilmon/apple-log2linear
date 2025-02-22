import os
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
import av
import numpy as np
import cv2
import shutil
import argparse
import concurrent.futures

def apple_log_decode(P):
    """
    Decode Apple Log-encoded pixel values into linear reflectance R.
    P can be a scalar or NumPy array (float32 or float64).

    The parameters (R0, RI, c, beta, gamma, delta) come from Apple's
    publicly available Apple Log White Paper.
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

def decode_and_save(
    arr, frame_idx,
    images_32bit_dir,
    images_16bit_dir,
    images_8bit_dir,
    color_correction=True
):
    """
    Decode Apple Log frame to linear, optionally apply color correction,
    then save:
      - 32-bit EXR
      - 16-bit PNG
      - 8-bit gamma-corrected PNG

    The input 'arr' is a 16-bit NumPy array (H, W, 3) with values [0..65535].
    """

    # 1) Convert integer [0..65535] to float [0..1]
    arr_float = arr.astype(np.float32) / 65535.0

    # 2) Decode from Apple Log to linear
    arr_lin = apple_log_decode(arr_float)

    # 3) If color_correction is True, apply Linear Rec.2020 → Linear Rec.709
    if color_correction:
        ccm = np.array([
            [  1.66075, -0.12420, -0.01810],
            [ -0.58790,  1.13300, -0.10060],
            [ -0.07250, -0.00830,  1.11950]
        ], dtype=np.float32)

        # Shape is (H,W,3). We can multiply by matrix.T using reshape + dot.
        arr_lin = arr_lin.reshape(-1, 3).dot(ccm).reshape(arr_lin.shape)

    # 4) Write 32-bit EXR (stay in float, no clamp)
    out_exr_path = os.path.join(images_32bit_dir, f'{frame_idx:06d}.exr')
    cv2.imwrite(out_exr_path, arr_lin[:, :, ::-1])  # OpenCV writes as BGR

    # 5) Convert to 16-bit integer PNG (clamp to [0..1], then scale by 65535)
    arr_lin_16 = np.clip(arr_lin, 0.0, 1.0) * 65535.0
    arr_lin_16 = arr_lin_16.astype(np.uint16)
    out_16bit_path = os.path.join(images_16bit_dir, f'{frame_idx:06d}.png')
    cv2.imwrite(out_16bit_path, arr_lin_16[:, :, ::-1])

    # 6) Convert to 8-bit gamma-corrected PNG
    gamma = 2.2
    arr_lin_gamma = np.power(np.clip(arr_lin, 0.0, 1.0), 1.0 / gamma)
    arr_lin_8 = (arr_lin_gamma * 255.0).astype(np.uint8)
    out_8bit_path = os.path.join(images_8bit_dir, f'{frame_idx:06d}.png')
    cv2.imwrite(out_8bit_path, arr_lin_8[:, :, ::-1])

def count_extractable_frames(container, step):
    """
    Returns how many frames in 'container' will be extracted
    if we skip frames according to 'step' (i.e. we only keep
    frames where global_frame_index % step == 0).
    """
    count = 0
    global_frame_index = 0
    for packet in container.demux():
        if packet.stream.type == 'video':
            for _ in packet.decode():
                # Same skip logic used in the main function
                if global_frame_index % step == 0:
                    count += 1
                global_frame_index += 1
    return count

def process_apple_log_video(base_dir, mov_filename, step, batch_size,color_correction=True):
    """
    - First, do a quick pass to see if the total # of extracted frames
      (with skipping) is < 10.
    - If < 10, just collect them all in memory in one pass, then save them
      at once.
    - Otherwise, keep a batch size of 10 frames for parallel saving.
    """

    # Construct paths
    tmp_dir = os.path.join(base_dir, 'tmp')
    images_32bit_dir = os.path.join(tmp_dir, 'images-32bit')
    images_16bit_dir = os.path.join(tmp_dir, 'images-16bit')
    images_8bit_dir  = os.path.join(tmp_dir, 'images')

    # Delete directories if they exist
    for d in (images_32bit_dir, images_16bit_dir, images_8bit_dir):
        if os.path.exists(d):
            shutil.rmtree(d)
    # Create directories
    os.makedirs(images_32bit_dir, exist_ok=True)
    os.makedirs(images_16bit_dir, exist_ok=True)
    os.makedirs(images_8bit_dir,  exist_ok=True)

    mov_path = os.path.join(base_dir, mov_filename)

    # -----------------------------------
    # 1) Count how many frames we'll extract
    # -----------------------------------
    print(f"Counting extractable frames with temporal downsample of {step}")
    container = av.open(mov_path)
    total_extractable = count_extractable_frames(container, step)
    container.close()
    print(f"Total frames after temporal downsample is {total_extractable}")

    # -----------------------------------
    # 2) Now we reopen & do the real pass
    # -----------------------------------
    container = av.open(mov_path)
    global_frame_index = 0
    saved_frame_index = 0

    frames_buffer = []

    # We'll gather frames in memory for final processing
    # if total_extractable < 10; otherwise, we do batch logic.
    use_batching = (total_extractable >= batch_size)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for packet in container.demux():
            if packet.stream.type == 'video':
                for frame in packet.decode():
                    if global_frame_index % step == 0:
                        # Convert to 16-bit from the original
                        rgb_frame = frame.reformat(format='rgb48le')
                        arr = rgb_frame.to_ndarray()  # (H, W, 3), dtype=uint16

                        frames_buffer.append((arr, saved_frame_index))
                        saved_frame_index += 1

                        # If we are batching and we've hit batch_size, flush
                        if use_batching and (len(frames_buffer) == batch_size):
                            futures = []
                            for arr_, idx_ in frames_buffer:
                                futures.append(
                                    executor.submit(
                                        decode_and_save,
                                        arr_,
                                        idx_,
                                        images_32bit_dir,
                                        images_16bit_dir,
                                        images_8bit_dir,
                                        color_correction
                                    )
                                )
                            concurrent.futures.wait(futures)
                            frames_buffer.clear()

                        # Periodically print progress
                        if saved_frame_index % batch_size == 0:
                            print(f"Processed {saved_frame_index} of {total_extractable} frames...")

                    global_frame_index += 1

        # End of container
        # If anything remains in frames_buffer, process it now
        if frames_buffer:
            futures = []
            for arr_, idx_ in frames_buffer:
                futures.append(
                    executor.submit(
                        decode_and_save,
                        arr_,
                        idx_,
                        images_32bit_dir,
                        images_16bit_dir,
                        images_8bit_dir,
                        color_correction
                    )
                )
            concurrent.futures.wait(futures)
            frames_buffer.clear()

    container.close()
    print(f"Finished processing {saved_frame_index} frames.")
    print(f"32-bit frames in: {images_32bit_dir}")
    print(f"16-bit frames in: {images_16bit_dir}")
    print(f"8-bit frames in:  {images_8bit_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process an Apple Log-encoded .mov video')
    parser.add_argument('--base_directory', type=str, required=True,
                        help='Base directory to create output folders')
    parser.add_argument('--mov_file', type=str, required=True,
                        help='Name of the .mov file (including extension)')
    parser.add_argument('--step', type=int, default=10,
                        help='Video temporal downsampling factor')
    parser.add_argument('--batch_size', type=int, default=30,
                        help='Number of frames to process in parallel')
    parser.add_argument('--apply_ccm', action='store_true',
                        help='Apply color correction?')

    args = parser.parse_args()

    process_apple_log_video(
        base_dir=args.base_directory,
        mov_filename=args.mov_file,
        step=args.step,
        batch_size=args.batch_size,
        color_correction=args.apply_ccm
    )
