# tracking/fairness_controller.py
from collections import defaultdict, deque
from typing import Dict, List

class FairnessController:
    def __init__(self, max_recognitions_per_person=10, recent_window_size=100):
        self.recognition_counts = defaultdict(int)
        self.recent_recognitions = deque(maxlen=recent_window_size)
        self.max_recognitions_per_person = max_recognitions_per_person
        
    def ensure_fair_attention(self, current_results: List[Dict]) -> List[Dict]:
        """Ensure no single person dominates system attention"""
        fair_results = []
        
        for result in current_results:
            identity = result.get('identity')
            if identity and identity != "Unknown":
                # Check if this person has been recognized too frequently
                recent_count = self._get_recent_recognition_count(identity)
                
                if recent_count < self.max_recognitions_per_person:
                    fair_results.append(result)
                    self.recognition_counts[identity] += 1
                    self.recent_recognitions.append(identity)
                else:
                    # Downgrade priority for over-represented persons
                    if 'priority_score' not in result:
                        result['priority_score'] = 1.0
                    result['priority_score'] *= 0.5  # Reduce priority
                    fair_results.append(result)
            else:
                fair_results.append(result)
        
        return fair_results
    
    def _get_recent_recognition_count(self, identity: str) -> int:
        """Count how many times this identity was recently recognized"""
        return sum(1 for rec in self.recent_recognitions if rec == identity)
    
    def get_fairness_stats(self) -> Dict:
        """Get fairness statistics"""
        return {
            'max_recognitions_per_person': self.max_recognitions_per_person,
            'recent_window_size': self.recent_recognitions.maxlen,
            'total_unique_identities': len(self.recognition_counts),
            'recent_recognitions_count': len(self.recent_recognitions)
        }
    
    def reset(self):
        """Reset fairness counters"""
        self.recognition_counts.clear()
        self.recent_recognitions.clear()