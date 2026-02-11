#!/usr/bin/env python3
"""
Script to train the document classifier ML model.

Usage:
    python scripts/train_classifier.py [training_data.csv]

Default training data location: backend/training_data/sample_training_data.csv
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stages.classifier_trainer import train_from_csv


def main():
    """Main function to train the classifier."""
    # Determine training data path
    if len(sys.argv) > 1:
        training_csv = sys.argv[1]
    else:
        # Default to sample training data
        backend_dir = Path(__file__).parent.parent
        training_csv = str(backend_dir / "training_data" / "sample_training_data.csv")

    print("=" * 70)
    print("Document Classifier Training Script")
    print("=" * 70)
    print(f"Training data: {training_csv}")
    print()

    # Check if file exists
    if not Path(training_csv).exists():
        print(f"✗ Error: Training data file not found: {training_csv}")
        print("\nPlease provide a CSV file with columns: filename, doc_type, text")
        sys.exit(1)

    # Train the model
    success = train_from_csv(
        csv_path=training_csv,
        model_dir=None,  # Will use default: backend/models/
        test_size=0.2,
        max_features=5000
    )

    if success:
        print("\n" + "=" * 70)
        print("✓ Training completed successfully!")
        print("=" * 70)
        print("\nModel saved to: backend/models/")
        print("  - classifier_model.joblib")
        print("  - classifier_vectorizer.joblib")
        print("\nThe classifier will now use the ML model for predictions.")
        sys.exit(0)
    else:
        print("\n" + "=" * 70)
        print("✗ Training failed!")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
