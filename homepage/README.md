# 마음체크 실행 안내

**이 폴더 전체만 있으면 실행할 수 있습니다.** 다른 프로젝트 폴더를 함께 받을 필요가 없습니다.

## 시작과 종료

- 시작: `마음체크_시작.cmd` 더블클릭
- 종료: `마음체크_종료.cmd` 더블클릭

첫 실행은 `payload`의 파일들을 확인하고 `실행묶음` 폴더에 풀기 때문에 몇 분 걸릴 수 있습니다. 이후 실행에서는 복원 과정을 건너뜁니다. 실행 주소는 매번 자동으로 열리며 `실행묶음/runtime/server.json`에도 기록됩니다.

다운로드가 완료된 후에는 인터넷과 별도 Python 설치가 필요하지 않습니다. Windows 64비트, NVIDIA GPU와 호환 드라이버가 필요하며 RTX 4070 Ti 12GB에서 검증했습니다.

## GitHub에서 이 폴더만 받기

Git과 Git LFS가 설치된 PowerShell에서 실행합니다.

```powershell
git lfs install
git clone --filter=blob:none --sparse https://github.com/jhakk100/r_scam_prototype.git
cd r_scam_prototype
git sparse-checkout set homepage
git lfs pull --include="homepage/payload/*"
```

GitHub의 ZIP 다운로드에는 모델이 아닌 LFS 포인터만 들어갈 수 있습니다. 위 방식으로 받은 `homepage` 폴더를 사용하세요. `payload` 파일 크기가 수백 바이트밖에 안 되거나 LFS 데이터 누락 오류가 나오면 저장소 안에서 마지막 `git lfs pull` 명령을 다시 실행합니다.

## 사용 순서

1. 텍스트를 붙여 넣거나 이미지를 선택해 문장을 추출합니다.
2. 문장 확인 화면에서 화자·대화 순서·개인정보를 확인합니다. 긴 대화는 목록 안에서 스크롤합니다.
3. 확인란을 체크하고 대화 분석을 시작합니다.
4. 위험 지수와 설명, 비슷한 대화 사례를 확인합니다. 결과 저장 버튼은 텍스트 파일을 내려받습니다.

이미지 인식은 글자나 화자를 잘못 읽을 수 있으므로 반드시 확인하세요. 대화 원문을 자동으로 파일에 저장하지 않습니다. 브라우저를 닫아도 서버는 실행 중일 수 있으므로 종료 파일을 사용하세요.

## 포함된 자원

`payload`는 검증된 실행 묶음을 무손실 압축한 분할 파일입니다. 원본 모델, 최종 어댑터와 토크나이저, 검색 사례 226건과 고정 설정, 분석 모듈, 한국어/영어 이미지 문장 인식 자산, 독립 Python과 GPU 라이브러리가 들어 있습니다.

개별 LFS 파일 크기 제한을 지키기 위해 여러 조각으로 나눴으며 시작 파일이 자동으로 이어서 복원합니다. 조각을 직접 합치거나 모델 파일을 별도로 구할 필요가 없습니다. 학습·논문·실험 폴더는 사용하지 않습니다.

압축 파일과 풀린 파일을 함께 보관할 수 있도록 약 40GB 이상의 디스크 여유 공간을 준비하세요. 전체 `homepage` 폴더를 복사하면 다른 위치에서도 사용할 수 있습니다. 모델이나 라이브러리를 새 버전으로 교체하면 기존 점수의 재현을 보장할 수 없습니다.

## 검증과 개발

- `payload/manifest.json`: 압축 조각의 크기·SHA-256
- `standalone-summary.json`: 실행 묶음 구성과 크기
- `standalone-runtime-lock.json`: 검증한 라이브러리 버전
- `standalone-verification.json`: 독립 실행·GPU 추론 검증 기록
- `실행묶음/manifest.json`: 복원된 개별 파일의 SHA-256
- `실행묶음/runtime/payload-verification.json`: 첫 복원 시 검사 결과

편집용 홈페이지 소스는 `app/`, 서버 코드는 `server.py`에 보관합니다. 기본 시작 파일은 검증된 `payload`를 실행합니다. 배포 파일을 다시 만들 때는 `build_standalone.py`로 새 묶음을 만든 뒤 `package_lfs.py`로 새 압축 조각을 준비하고 재검증합니다.

결과는 참고 정보이며 실제 범죄 여부나 상대방의 안전성을 확정하지 않습니다.
