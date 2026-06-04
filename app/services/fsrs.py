from datetime import datetime, timedelta, timezone

class FSRSLite:
    """
    簡易版間隔重複演算法 (FSRS-Lite)
    用於計算下一次複習的日期與大腦記憶參數
    """
    @staticmethod
    def calculate_next_review(rating: int, stability: float, difficulty: float) -> dict:
        """
        rating: 1(忘記 Again), 2(困難 Hard), 3(普通 Good), 4(簡單 Easy)
        stability: 記憶穩定度 (視為預估記憶天數)
        difficulty: 難度 (數值越高代表越難)
        """
        # 初次複習初始化
        if stability <= 0:
            stability = 1.0
        if difficulty <= 0:
            difficulty = 5.0
        
        # 1. 更新難度 Difficulty
        if rating == 1:
            difficulty = min(10.0, difficulty + 1.5)
        elif rating == 2:
            difficulty = min(10.0, difficulty + 0.5)
        elif rating == 3:
            difficulty = max(1.0, difficulty - 0.5)
        elif rating == 4:
            difficulty = max(1.0, difficulty - 1.5)
            
        # 2. 更新穩定度 Stability (下次複習間隔)
        if rating == 1:
            stability = max(1.0, stability * 0.2)
        elif rating == 2:
            stability = stability * 1.2
        elif rating == 3:
            stability = stability * 2.5
        elif rating == 4:
            stability = stability * 3.5
        
        # 3. 計算下次到期日
        next_due_date = datetime.now(timezone.utc) + timedelta(days=stability)
        
        return {
            "stability": round(stability, 4),
            "difficulty": round(difficulty, 4),
            "due_date": next_due_date.isoformat()
        }
