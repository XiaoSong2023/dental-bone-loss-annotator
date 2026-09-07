# Periodontal Alveolar Bone-Loss Models (DenPAR) — v2

- `surf_pose.pt` / `.onnx` — YOLOv8m-pose. One instance = one tooth SURFACE,
  3 keypoints: [0]=CEJ, [1]=bone-crest∩tooth intersection, [2]=Apex.
- `tooth_seg.pt` / `.onnx` — YOLOv8s-seg tooth masks (for the pattern stage).

## Inference recipe (must match training)
- imgsz=768, conf=0.25, iou=0.5; drop a surface if any keypoint conf < 0.30
- severity = along-axis projection of the intersection onto the CEJ→Apex axis,
  as a fraction of root length ×100 (skip if root length < 30 px)
- Staging: <15 I, 15-33 II, 33-50 III, >=50 IV

## Reported performance (matched surfaces, test set)
- Severity ICC(2,1) ≈ 0.88 (0.87 under the paper's min-max formula); recall ≈ 81%
