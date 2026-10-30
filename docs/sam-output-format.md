# SAM 3.1 output format (verified)

What the Meta Model API actually returns for `sam-3.1`. Verified on Oct 26, 2026 with synthetic test
images (three 41×41 circles on 256×256; one 160×40 rectangle on 320×200), cross-checked against
<https://dev.meta.ai/docs/sam/reading-segmentation>.

## Request

OpenAI SDK, Responses API, base URL `https://api.meta.ai/v1`:

```python
client.responses.create(
    model="sam-3.1",
    metadata={"mask_encoding": "one_bit"},   # or "lossless" (default)
    input=[{"role": "user", "content": [
        {"type": "input_text", "text": "nut"},                     # one short noun phrase
        {"type": "input_image", "image_url": "data:image/png;base64,..."},
    ]}],
)
```

The result is plain text in `response.output[0].content[0].text`.

## Response text

```
<0f>0<|box;x1=180;y1=108;x2=220;y2=148;w=256;h=256|><|mask;x=0;y=0;data=41,41,!...|>,1<|box;...|><|mask;...|>,...
```

- `<0f>` marks frame 0. A single image is always frame 0.
- Each record is `<object_id><|box;...|><|mask;...|>`, and records are separated by commas.
- **No matches returns an empty string.** That's a valid result (zero instances), not an error.

### Box

- `x1,y1,x2,y2` are pixel corners in the source image, **inclusive**: a 160 px wide object gives
  `x2 - x1 = 159`.
- `w,h` are the source image width and height, repeated on every record.

### Mask

- `data=<H>,<W>,<payload>`. **Height comes first.** The 160×40 rectangle returned `data=40,160`.
- The mask is **cropped to the box**: `H = y2 - y1 + 1`, `W = x2 - x1 + 1`. To get a full-image mask,
  paste it at `(y1, x1)`.
- The first character of the payload names the encoding: `~` = lossless, `!` = one_bit.
- `x=0;y=0` are always literal zeros.

## Decoding

Use Meta's `meta-sam-parser` (0.1.0, no dependencies):

```python
from meta_sam_parser import SegmentationMask, decode_mask_to_raster

mask = SegmentationMask(encoding="one_bit",   # "lossless" for "~"
                        payload=payload,      # includes the leading encoding char
                        width=W, height=H)
raster: bytes = decode_mask_to_raster(mask)  # row-major, H*W bytes of 0/1
```

## Encoding choice

On the test shapes, `one_bit` and `lossless` decoded to identical masks. The responses were
390 vs 2,043 characters for the circles and 13 vs 2,250 for the rectangle. Inspec requests `one_bit`.

## Large masks are downscaled (found Oct 30)

For a large object (Breakfast Box granola, box 835x1062 px) SAM returned an 805x1024 mask: the long
side is capped at 1024 px and the other side scaled by the same factor. `parse_sam_output` accepts
exactly that case and resizes the mask back to the box with nearest-neighbour; any other mismatch
between mask and box dimensions is still an error.
