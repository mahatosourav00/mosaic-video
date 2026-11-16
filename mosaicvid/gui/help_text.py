"""Plain-language help for every option: key -> (title, explanation, recommendation or "")."""

HELP: dict[str, tuple[str, str, str]] = {
    # ---- photos
    "tiles_folder": ("Your photos",
                     "The folder with all the photos that will become the small tiles. Photos inside its sub-folders are "
                     "included too (you can switch that off), and you can add more folders. "
                     "More photos means a more varied mosaic; around 300 or more looks best.",
                     "A few hundred photos for a rich result."),
    "subfolders": ("Include photos in sub-folders",
                   "When on, photos inside folders within your chosen folder are used too. Switch it off to use only "
                   "the photos directly in the folder. You can also leave out particular folders (for example "
                   "screenshots or a folder of scans).", "On"),
    "main_image": ("Main picture",
                   "The big picture your mosaic will recreate from the tiles. Pick one with a clear subject, such as a "
                   "face or a simple scene. Busy backgrounds turn into noise.",
                   "A sharp portrait with a plain background."),
    "existing": ("Use a mosaic I already built",
                 "Skip building the mosaic and make a new video from one you created before (a scene.json file). "
                 "It is quick, so it is perfect for trying different animation styles.", ""),
    "shape": ("Shape",
              "The proportions of your mosaic and video. It is chosen before the mosaic is built, so the photos fill "
              "the frame exactly. Story (9:16) suits phones; Square suits feeds; Wide suits TVs and YouTube.",
              "Story for Instagram / Reels / Shorts."),
    # ---- prepare
    "prep_skip": ("Skip all preparation",
                  "Use your photos exactly as they are, with no cleaning. Every photo is still cropped to a square. "
                  "Choose this if you already cleaned your photos, or to save time.", ""),
    "prep_trim": ("Trim borders and frames",
                  "Removes white or black frames and thin borders around photos (screenshots, framed prints, "
                  "chat-app photos) so they do not show as stripes in the mosaic.", "On"),
    "prep_dedupe": ("Remove duplicates",
                    "Finds near-identical photos (burst shots, the same picture saved twice) and keeps only one, so "
                    "the same face does not appear next to itself.", "On"),
    "prep_filter": ("Skip blurry and tiny photos",
                    "Leaves out photos that are too blurry or too small. They would only look like smudges at tile "
                    "size.", "On"),
    "prep_crop": ("Smart square crop",
                  "Tiles are squares. Smart crop keeps the part of each photo with faces and detail instead of "
                  "cutting a plain square from the middle.", "On"),
    "prep_rotate": ("Fix sideways photos (experimental)",
                    "Tries to turn sideways or upside-down photos upright by looking for faces. It is not always "
                    "right, so check the review sheet if you switch it on.", "Off for now"),
    "min_sharpness": ("Blur strictness",
                      "How sharp a photo has to be to be kept. Raise it to drop more soft photos; lower it if "
                      "good photos are being removed.", "Default"),
    "min_side": ("Smallest photo size",
                 "Photos with a shorter side below this many pixels are left out.", "96 px"),
    # ---- look
    "preset": ("Quality preset",
               "One-click starting points. Quick draft is fast to try ideas; Balanced is right for most people; "
               "Best quality makes a larger, more detailed mosaic but takes longer.", "Balanced"),
    "detail": ("Detail",
               "How many tiles the picture is made of. More tiles means finer detail and a bigger, slower build. "
               "Fewer tiles looks chunkier and bolder. You need enough different photos to avoid too many repeats.",
               "1,500 to 3,000"),
    "repeats": ("Most times one photo can appear",
                "Limits how often the same photo is used. Lower values look more varied but need more photos. "
                "Auto picks a sensible limit from your photo count.", "Auto"),
    "spread": ("Keep repeats apart",
               "Stops copies of the same photo from sitting close together. Higher numbers spread them further "
               "apart, but are harder to satisfy with few photos.", "6"),
    "colour": ("Colour match",
               "Gently tints each tile toward the colour of the picture underneath. More makes the main picture "
               "clearer; less keeps the photos' own colours.", "Around 60%"),
    "faces": ("Focus on faces and subject",
              "Spends extra care getting faces and the main subject right, at the expense of the background. "
              "Great for portraits.", "On, around 60%"),
    "grayscale": ("Black and white",
                  "Makes the whole mosaic black and white: the tiles and the main picture. It gives a classic, "
                  "dramatic look and often reads more clearly from far away.", "Off, unless you want the classic look"),
    "gap_color": ("Gap colour",
                  "The colour of the thin line between tiles when a gap is set. Black looks like grout in a dark "
                  "mosaic; white looks like a light frame around each tile.", "Black"),
    "print_size": ("Output size",
                   "Screen is quick and sized for viewing on a display. Print size makes the image big and sharp enough "
                   "for a poster at the size and DPI you choose, and saves the DPI inside the file so print shops "
                   "get it right. 300 DPI is standard for printing; 150 is fine for large posters seen from a "
                   "distance.", "Screen for sharing, Print for posters"),
    "preview": ("Preview before building",
                "Builds a small, fast draft so you can check the arrangement and colours before spending time on "
                "the final result. The final mosaic has exactly the same arrangement, just sharper.", ""),
    "blend": ("Main picture showing through",
              "Lays a faint copy of the main picture over the mosaic image. A little helps it read from a distance; "
              "too much hides the tiles.", "10 to 15%"),
    "size": ("Image sharpness",
             "How many pixels each tile gets in the saved image. Bigger is sharper and good for printing, but makes "
             "a larger file and takes longer.", "Standard for screens, Large for print"),
    "image_format": ("Image file type",
                     "PNG is lossless and best for printing or editing. JPEG is small and works everywhere. WebP is "
                     "small and modern. TIFF is lossless and used by print shops and photo editors; the files are "
                     "large.", "PNG for quality, JPEG to share"),
    "image_quality": ("JPEG / WebP quality",
                      "Higher keeps more fine detail but makes a bigger file. 90 and above is visually lossless.",
                      "90 to 95"),
    "subtiles": ("Extra fine detail (small tiles)",
                 "Splits some tiles into four smaller ones in the busiest areas, such as eyes and hair, for a "
                 "sharper face. Works best with many photos.", "On if you have 400+ photos"),
    "subtile_percent": ("How much to split",
                        "The share of tiles that get split into smaller ones. Splitting more adds detail but "
                        "makes the repeat rules harder to meet.", "20 to 25%"),
    "even_usage": ("Use all photos evenly",
                   "Pushes the builder to use every photo about the same number of times instead of favouring "
                   "a few lucky ones.", "50%"),
    "flip": ("Allow mirrored photos",
             "Lets a photo be flipped left-to-right to fit better. It gives a closer match, but flipped text "
             "will look backwards.", "On"),
    "gap": ("Gap between tiles",
            "A thin line between tiles, like grout. 0 is seamless.", "0"),
    "seed": ("Variation number",
             "The mosaic is built with a bit of randomness. The same number always gives the same result; "
             "change it to get a different arrangement.", ""),
    # ---- video
    "video_style": ("Animation style",
                    "How the tiles arrive and how the camera moves. Each style has its own camera: Swarm orbits and "
                    "sweeps, Vortex circles the subject, Wave tracks sideways along a sweeping reveal, Zoom pulls "
                    "straight back from a close-up.", "Try each one with a Draft preview first."),
    "length": ("Length",
               "How long the video is, in seconds. Longer videos give the animation more room but make bigger files "
               "and take longer to render.", "15 to 25 seconds"),
    "quality": ("Video quality",
                "Draft is a fast, small preview for judging motion and style. Standard is crisp for sharing. High "
                "keeps more detail in dark areas but makes the file about twice the size.", "Draft while "
                "exploring, then Standard"),
    "format": ("File type",
               "MP4 works everywhere. MP4 (H.265) is smaller but some older apps cannot play it. WebM is for the web. "
               "GIF is short, silent and large, so keep it brief.", "MP4"),
    "resolution": ("Video resolution",
                   "How sharp the video is. 720p is small and quick, 1080p (Full HD) suits phones and most screens, "
                   "1440p and 4K are crisper but take much longer to render and make big files. Draft preview "
                   "ignores this.", "1080p"),
    "fps": ("Smoothness (frames per second)",
            "30 is standard and smooth. 60 is silkier but doubles render time and file size.", "30"),
    "showcase": ("Showcase photos",
                 "How many photos fly large through the foreground so viewers can see them. 0 turns them off.",
                 "12 to 18"),
    "dof": ("Depth blur",
            "Blurs tiles that are away from the focus, like a real camera. It adds depth and a premium feel.",
            "About 70%"),
    "glow": ("Glow and shadow",
             "A soft shadow and glow around the finished mosaic that lifts it off the background.", "About 60%"),
    "particles": ("Floating dust",
                  "Tiny drifting sparkles in the air. They add atmosphere. 0 turns them off.", "100 to 250"),
    "backdrop": ("Blurred backdrop",
                 "A dark, blurred copy of your main picture behind the mosaic instead of a flat colour.", "On"),
    "pulses": ("Arrival waves",
               "Tiles land in this many bursts, with calm moments in between. 0 is a constant stream.", "3 to 5"),
    "output_folder": ("Where to save",
                      "Everything is saved into this folder: the mosaic image, the video, and the files that let you "
                      "make new videos later.", ""),
}
