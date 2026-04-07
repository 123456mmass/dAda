# Laboratory Data Vector Group Mapping

This document provides the definitive vector group mapping for the 15 experimental groups in the laboratory dataset. This mapping was derived using **Matrix Matching (PU Error Minimized)** and validated by **Group 5 (Y-d)** as a ground truth anchor.

## 📊 Summary of Vector Group Mappings

| Vector Group | Folder Names | Reasoning |
| :--- | :--- | :--- |
| **Yd11 (HV:Y, LV:d)** | กลุ่ม 1, 2, 5, 8, 13, 15 | **Group 5 Anchor**, High I4 (~4A), Ratio ~1.2/2.5 |
| **Dy11 (HV:D, LV:y)** | กลุ่ม 7, 14 | Ratio = 1.00 exactly, Low I4 (~1.8A) |
| **Yy0 (HV:Y, LV:y)** | กลุ่ม 10 | **Best Fit (Idiff 0.32)**, Ratio ~3.0 |
| **Dd0 (HV:D, LV:d)** | กลุ่ม 3, 4, 11, 12 | Standard Step-down ratio (2.5), Low I4 |

---

## 🛠️ Methodology

1.  **I4 Fingerprinting:** We observed that Star (Y) connections consistently exhibit higher neutral current (I4) readings in this laboratory setup compared to Delta (d) connections.
2.  **Ratio Matching:** We calculated $I_{LV\_RMS} / I_{HV\_ref}$ to distinguish between 1:1 ($Ratio \approx 1.0$) and 2:1 ($Ratio \approx 2.0-3.1$) winding configurations.
3.  **Matrix Matching:** Each group was tested against **Dd0, Yy0, Yd11, and Dy11** matrices. The group was assigned to the matrix that produced the lowest median $I_{diff}$ across the experimental phase.

## 📁 Repository Integration
The mapping is used by `backend/scripts/run_lab_eval.py` to automatically select the correct vector group for each folder during performance evaluation.
