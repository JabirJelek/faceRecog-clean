#### Below is for structure detail in references

knowledge/references/
├── patterns/ # Design patterns you've implemented
│ ├── singleton_logging.md
│ ├── pipeline_processing.md
│ └── factory_configs.md
├── algorithms/ # Algorithm implementations (even if deprecated)
│ ├── face_recognition_v1.py
│ ├── mask_detection_temporal.py
│ └── tracking_algorithm_comparison.md
├── experiments/ # Experimental approaches with learnings
│ ├── alternative_face_detectors/
│ │ ├── mtcnn_approach.py
│ │ └── results_comparison.md
│ └── gpu_optimization_tests/
│ ├── mixed_precision_test.py
│ └── performance_analysis.md
└── integrations/ # Code for external services
├── websocket_server_v1.py
└── third_party_api_connectors/

#### Below is for structure detail in history

    knowledge/history/

├── logs/ # Archived log files (read-only)
│ ├── 2023-10_performance_tests.log
│ └── 2024-01_production_issues.log
├── snapshots/ # Complete project states at milestones
│ ├── v0.5_pre_modular/
│ ├── v0.8_multiprocessing/
│ └── v1.0_release_candidate/
└── decisions/ # Documentation of why choices were made
├── why_chose_yolo_over_mtcnn.md
├── architecture_refactor_2023.md
└── dependency_upgrade_risks.md

#### Below is explanation from above classification folder

📝 How to Classify Your Files

- Reference Category (Put in knowledge/references/):

  Deprecated but insightful code: Methods that worked well but were replaced due to performance, not correctness

  Alternative implementations: Different approaches to the same problem

  Utility functions: Helper code that might be reusable in other contexts

  Configuration templates: Old configs that show evolution of settings

  Integration examples: Code connecting to external services

Example: Your old simple_tracker.py that was replaced by byte_tracker.py belongs in knowledge/references/algorithms/ with a note explaining when the simpler approach might still be useful.

- History Category (Put in knowledge/history/):

  Log files: Raw logs from past runs (compress if large)

  Complete deprecated versions: When entire folders are replaced

  Backup files: Temporary or backup copies

  Screenshots/visuals: Old UI layouts or output examples

  Meeting notes: Development discussions

Example: Your logs/debug_2024_01_15.log moves to knowledge/history/logs/ and won't be referenced regularly.

#### If we want to fill out the file in the references / history, it would be better that we provide reasons for such things. Below is the expected structure if we want to move into references / history.

`# ==============================================
`# DEPRECATED: {Fill out reason of the status, consist of 3 status: [DEPRECATED], [ALTERNATIVE], [REFERENCE]. This status is only for banner, provide reason in the provided section.}
`# REASON: {Reason why status above was palced in the current file}
`# LEARNINGS: {What can be understood from this file}
`# REFERENCE: {Even if this file was not utilized anymore, where is the effective range for this file.}
`# ==============================================
