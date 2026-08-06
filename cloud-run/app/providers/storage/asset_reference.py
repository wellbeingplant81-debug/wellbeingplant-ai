"""
EPIC Instagram Connector (Production) - AssetReference.

"Local File -> Public Asset -> AssetReference"라는 플랫폼 공통 계약의
결과 모양이다. Instagram 하나 때문에 만든 것이 아니다 - 앞으로 TikTok/
Facebook/Threads/AI Bridge/Business OS 등 어떤 소비자든 재사용할 수
있도록, 특정 플랫폼의 파라미터명(video_url, media_url 등)을 흉내내지
않고 순수 데이터만 담는다.

YouTube는 local_path만 있으면 충분하고(직접 파일 업로드), Instagram은
public_url이 있어야 한다(Graph API가 공개 URL만 받는다) - 어느 필드가
채워지는지는 실제로 만든 AssetPublisher 구현체가 결정한다. 이 dataclass
자신은 아무 것도 검증/추측하지 않는다 - 순수 데이터 컨테이너다.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AssetReference:

    local_path: str = ""
    public_url: str = ""
    mime_type: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None
