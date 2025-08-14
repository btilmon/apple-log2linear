
<p align="center">
  <img src="assets/2001.jpg" width="250"/>
</p>


Apple ProRes Log video format captures minimally processed 10 bit HDR video up to 4K 30FPS on iPhone 15 and 16 Pros. The videos are radiometrically and geometrically calibrated by Apple on device. This makes ProRes Log video one of the easiest ways to get film quality calibrated video for photogrammetry, radiance fields, VFX, and so on without needing a full frame camera and manual calibrations. Apple promises that after decoding from log to linear, the image values represent linear scene reflectance, which is usually hard to get on iPhones due to all the computational photography processing. This repo implements the log to linear decoding based on the [Apple Log Profile White Paper](Apple_Log_Profile_White_Paper.pdf).

## Radiometric Linearity Test

After decoding the log images to linear, the image intensity should increase linearly based on the exposure ratio. For example, if the exposure is increased from 1 second to 2 seconds, the average image intensity should increase 2x. This was tested by setting the first GT value to the first real average image intensity, and then multiplying it by the known exposure ratio for each exposure. The real image intensities at each exposure are then compared to this GT to test if the decoded linear images are actually linear. The following plot suggests strong linearity of the decoded linear images.

<p align="center">
  <img src="assets/radiometric-linearity.png" width="500px"/>
</p>


## How to turn on ProRes Log video format

Go to `Settings->Camera->Formats` and at the bottom turn on Apple ProRes and select Log from ProRes Encoding. When you open the camera app, you should see `ProRes LOG` in the top left if it is on. At 4K 30FPS, a 1 minute video is around 6GB. 

<p align="center">The video color will look flat during capture due to the log encoding:</p>
<p align="center">
  <img src="assets/log.png" width="500px"/>
</p>


## Recommended steps for improved radiometry
I recommend using the Blackmagic camera app for more manual control over each camera setting, but these recommended steps assume the default iPhone camera app is being used. For example, in the Blackmagic camera app you can set the color space to Rec.2020 - HDR which in theory should save out a linear decoded video, but I don't know for sure, so I implemented this repo to be sure.
* Use the 0.5x ultrawide camera with locked auto exposure and locked auto focus while underexposing to prevent motion blur. To do this, hold down on the screen when the camera app is open and the `AE/AF` will lock, which locks the auto exposure and auto focus. Unfortunately it is not possible to lock one of focus or exposure, they both have to be locked. Using the 0.5x ultrawide camera has the largest depth of field which helps prevent being out of focus when locking. Scrolling down on the exposure slider will decrease motion blur by shortening exposure. I find it beneficial to deliberately underexpose for most scenes, there is usually enough signal and it decreases motion blur. 
* Turn on `Lock Camera` and `Lock White Balance` in `Settings->Camera->Record Video`
* Turn on `Lens Correction` in `Settings->Camera` for undistortion

## Optional Color Correction
Per the white paper, the images are in Linear Rec.2020 after decoding. If you want more visually appealing images, at the expense of a compressed color range, use `--apply_ccm` to convert from Linear Rec.2020 to Linear Rec.709 based on D65 illuminant. The 8 bit images will still have gamma correction applied to them. This color correction is off by default. Here is the difference between the two:
 <p align="center">
  <img src="assets/ccm.png"/>
</p>

  
## Instructions

Non standard dependencies to install:
* `pip install av`
* `pip install opencv-python`

Capture the video and then download the .MOV file from your phone to your computer. It is fastest to transfer over usb wire but google drive can be used at slower speed. A sample video is provided.

```bash
python apple-log2linear.py --base_directory . --mov_file IMG_2910.MOV 
```

Run the following to see all command line options:
```bash
python apple-log2linear.py -h
```

The data is saved to 3 folders inside the generated `tmp` folder:
* `images` - 8 bit gamma corrected and clipped for COLMAP etc
* `images-16bit` - 16 bit PNG with clipped linear 10 bit data for ease of use
* `images-32bit` - 32 bit EXR with unclipped linear 10 bit data for maximum fidelity


