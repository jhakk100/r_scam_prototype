#!/usr/bin/env python3

# ============================================================
# CHECK_ENV.py
# Gemma 4 E2B QLoRA 학습환경 검사기
# ============================================================

import sys
import subprocess
import shutil
import importlib
from pathlib import Path
from importlib.metadata import version as package_version
from importlib.metadata import PackageNotFoundError


# ============================================================
# 프로젝트 표준 환경
# ============================================================

REQUIRED_PYTHON = (3, 11, 6)

REQUIRED_PACKAGES = {
    "torch": "2.7.0",
    "transformers": "5.14.1",
    "peft": "0.20.0",
    "trl": "1.9.2",
    "accelerate": "1.14.0",
    "bitsandbytes": "0.50.2",
    "datasets": "5.0.1",
    "safetensors": "0.8.0",
}

# CHECK_ENV 자체에서 사용하는 보조 패키지
# 학습환경 핵심 라이브러리가 아니므로 버전은 강제하지 않음
HELPER_PACKAGES = [
    "psutil",
]

REQUIRED_CUDA_RUNTIME = "12.6"

TORCH_INDEX_URL = (
    "https://download.pytorch.org/whl/cu126"
)

AUTO_INSTALL_MISSING = True


# ============================================================
# 출력용
# ============================================================

ERRORS = []
WARNINGS = []
FIX_COMMANDS = []


def section(title):
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def ok(message):
    print(f"[PASS] {message}")


def warning(message):
    print(f"[WARN] {message}")
    WARNINGS.append(message)


def error(message):
    print(f"[FAIL] {message}")
    ERRORS.append(message)


# ============================================================
# Python 버전 확인
# ============================================================

def check_python():

    section("1. Python 버전 검사")

    current = sys.version_info[:3]

    print(
        f"현재 Python : "
        f"{current[0]}.{current[1]}.{current[2]}"
    )

    print(
        f"필요 Python : "
        f"{REQUIRED_PYTHON[0]}."
        f"{REQUIRED_PYTHON[1]}."
        f"{REQUIRED_PYTHON[2]}"
    )

    if current == REQUIRED_PYTHON:

        ok("Python 버전 정상")

        return

    print()
    print("[CRITICAL] Python 버전이 프로젝트 표준과 다릅니다.")
    print()
    print("Python은 실행 중인 환경에서 자동 교체하지 않습니다.")
    print("Python 3.11.6을 설치한 후 새로운 가상환경을 생성하십시오.")
    print()

    print("Linux / macOS (pyenv 사용 예시)")
    print("--------------------------------")
    print("pyenv install 3.11.6")
    print("pyenv local 3.11.6")
    print("python -m venv .venv")
    print("source .venv/bin/activate")
    print()

    print("Windows")
    print("--------------------------------")
    print("Python 3.11.6 x64 설치 후:")
    print()
    print("py -3.11 -m venv .venv")
    print(r".venv\Scripts\activate")
    print()

    print("Python 버전 수정 후 CHECK_ENV.py를 다시 실행하십시오.")

    sys.exit(1)


# ============================================================
# pip 확인
# ============================================================

def ensure_pip():

    section("2. pip 검사")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "--version",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode == 0:

        ok(result.stdout.strip())

        return

    warning("pip를 찾을 수 없습니다. ensurepip 실행")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ensurepip",
            "--upgrade",
        ]
    )

    if result.returncode != 0:

        print()
        print("[CRITICAL] pip 설치 실패")
        print("Python 환경을 확인하십시오.")

        sys.exit(1)

    ok("pip 설치 완료")


# ============================================================
# 설치 여부 검사
# ============================================================

def get_installed_version(name):

    try:
        return package_version(name)

    except PackageNotFoundError:
        return None


def strip_build_tag(version_string):
    """
    2.7.0+cu126 -> 2.7.0
    """

    return version_string.split("+")[0]


def install_package(name, target_version=None):

    print()

    if target_version:
        spec = f"{name}=={target_version}"
    else:
        spec = name

    print(f"[INSTALL] {spec}")

    if name == "torch":

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            spec,
            "--index-url",
            TORCH_INDEX_URL,
        ]

    else:

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            spec,
        ]

    result = subprocess.run(command)

    if result.returncode != 0:

        print()
        print(f"[CRITICAL] {name} 설치 실패")

        sys.exit(1)

    importlib.invalidate_caches()

    print(f"[INSTALL COMPLETE] {spec}")


def check_and_install_packages():

    section("3. 필수 라이브러리 검사")

    # ---------------------------------------
    # 핵심 패키지
    # ---------------------------------------

    for name, required_version in REQUIRED_PACKAGES.items():

        installed = get_installed_version(name)

        if installed is None:

            print(f"[MISSING] {name}")

            if AUTO_INSTALL_MISSING:

                install_package(
                    name,
                    required_version,
                )

            else:

                error(f"{name} 미설치")

            continue

        installed_base = strip_build_tag(installed)

        if installed_base == required_version:

            ok(
                f"{name}: "
                f"{installed}"
            )

        else:

            error(
                f"{name} 버전 불일치 "
                f"(현재 {installed}, "
                f"필요 {required_version})"
            )

            if name == "torch":

                FIX_COMMANDS.append(
                    f"{sys.executable} -m pip install "
                    f"--upgrade --force-reinstall "
                    f"torch=={required_version} "
                    f"--index-url {TORCH_INDEX_URL}"
                )

            else:

                FIX_COMMANDS.append(
                    f"{sys.executable} -m pip install "
                    f"--upgrade --force-reinstall "
                    f"{name}=={required_version}"
                )

    # ---------------------------------------
    # CHECK_ENV 보조 패키지
    # ---------------------------------------

    for name in HELPER_PACKAGES:

        installed = get_installed_version(name)

        if installed is None:

            print(f"[MISSING] {name}")

            if AUTO_INSTALL_MISSING:

                install_package(name)

        else:

            ok(
                f"{name}: "
                f"{installed}"
            )


# ============================================================
# 실제 라이브러리 import
# ============================================================

def import_packages():

    section("4. 라이브러리 Import 검사")

    global torch
    global transformers
    global peft
    global trl
    global accelerate
    global bitsandbytes
    global datasets
    global safetensors
    global psutil

    try:

        import torch
        import transformers
        import peft
        import trl
        import accelerate
        import bitsandbytes
        import datasets
        import safetensors
        import psutil

        ok("모든 라이브러리 Import 성공")

    except Exception as e:

        error(
            f"라이브러리 Import 실패: {e}"
        )

        print()
        print(
            "패키지 설치 직후 Import 오류가 발생했다면 "
            "터미널을 재실행하거나 가상환경을 다시 활성화한 뒤 "
            "CHECK_ENV.py를 다시 실행하십시오."
        )

        final_result()

        sys.exit(1)


# ============================================================
# 실제 import된 패키지 버전 재검사
# ============================================================

def check_runtime_versions():

    section("5. 실제 로드된 라이브러리 버전")

    packages = {
        "torch":
            strip_build_tag(torch.__version__),

        "transformers":
            transformers.__version__,

        "peft":
            peft.__version__,

        "trl":
            trl.__version__,

        "accelerate":
            accelerate.__version__,

        "bitsandbytes":
            bitsandbytes.__version__,

        "datasets":
            datasets.__version__,

        "safetensors":
            safetensors.__version__,
    }

    for name, version in packages.items():

        required = REQUIRED_PACKAGES[name]

        if version == required:

            ok(
                f"{name}: "
                f"{version}"
            )

        else:

            error(
                f"{name}: "
                f"{version} "
                f"(필요 {required})"
            )


# ============================================================
# CUDA / GPU 검사
# ============================================================

def check_cuda():

    section("6. CUDA / GPU 검사")

    if not torch.cuda.is_available():

        error("CUDA 사용 불가")

        print(
            "PyTorch가 NVIDIA GPU를 인식하지 못합니다."
        )

        return None

    ok("CUDA 사용 가능")

    # PyTorch CUDA runtime
    runtime = torch.version.cuda

    print(
        f"PyTorch CUDA Runtime : {runtime}"
    )

    if runtime == REQUIRED_CUDA_RUNTIME:

        ok(
            f"CUDA Runtime {runtime}"
        )

    else:

        error(
            f"CUDA Runtime 불일치 "
            f"(현재 {runtime}, "
            f"필요 {REQUIRED_CUDA_RUNTIME})"
        )

    # GPU 개수
    device_count = torch.cuda.device_count()

    print(
        f"CUDA GPU 개수 : {device_count}"
    )

    gpu_infos = []

    for device_index in range(device_count):

        props = torch.cuda.get_device_properties(
            device_index
        )

        vram_gb = (
            props.total_memory
            / (1024 ** 3)
        )

        major, minor = (
            torch.cuda.get_device_capability(
                device_index
            )
        )

        info = {
            "index": device_index,
            "name": props.name,
            "vram": vram_gb,
            "compute_capability":
                f"{major}.{minor}",
        }

        gpu_infos.append(info)

        print()
        print(
            f"GPU {device_index}"
        )
        print(
            f"  이름               : "
            f"{props.name}"
        )
        print(
            f"  VRAM               : "
            f"{vram_gb:.2f} GB"
        )
        print(
            f"  Compute Capability : "
            f"{major}.{minor}"
        )

    # 가장 VRAM이 큰 GPU 사용
    target_gpu = max(
        gpu_infos,
        key=lambda x: x["vram"]
    )

    print()
    print(
        f"QLoRA 기준 GPU : "
        f"GPU {target_gpu['index']} "
        f"({target_gpu['name']})"
    )

    # BF16
    try:

        torch.cuda.set_device(
            target_gpu["index"]
        )

        bf16_supported = (
            torch.cuda.is_bf16_supported()
        )

    except Exception:
        bf16_supported = False

    if bf16_supported:

        ok("BF16 지원")

    else:

        warning(
            "BF16 미지원 - FP16 사용 필요"
        )

    return {
        "gpu": target_gpu,
        "bf16": bf16_supported,
    }


# ============================================================
# bitsandbytes 실제 NF4 연산 테스트
# ============================================================

def check_bitsandbytes():

    section(
        "7. bitsandbytes CUDA Backend 검사"
    )

    if not torch.cuda.is_available():

        error(
            "CUDA 사용 불가로 bitsandbytes 테스트 생략"
        )

        return False

    try:

        device = torch.device("cuda")

        test_layer = (
            bitsandbytes.nn.Linear4bit(
                16,
                16,
                bias=False,
                compute_dtype=torch.bfloat16,
                compress_statistics=True,
                quant_type="nf4",
            )
        )

        test_layer = test_layer.to(device)

        test_input = torch.randn(
            1,
            16,
            device=device,
            dtype=torch.bfloat16,
        )

        with torch.no_grad():

            output = test_layer(
                test_input
            )

        torch.cuda.synchronize()

        if output.shape != (1, 16):

            raise RuntimeError(
                "bitsandbytes 출력 shape 비정상"
            )

        ok(
            "bitsandbytes NF4 CUDA 연산 정상"
        )

        del test_layer
        del test_input
        del output

        torch.cuda.empty_cache()

        return True

    except Exception as e:

        error(
            "bitsandbytes CUDA backend 비정상"
        )

        print(
            f"오류 내용: {e}"
        )

        return False


# ============================================================
# 시스템 RAM / 디스크
# ============================================================

def check_system_resources():

    section("8. 시스템 자원 검사")

    # RAM
    ram = psutil.virtual_memory()

    total_ram_gb = (
        ram.total
        / (1024 ** 3)
    )

    available_ram_gb = (
        ram.available
        / (1024 ** 3)
    )

    print(
        f"RAM 전체 : "
        f"{total_ram_gb:.2f} GB"
    )

    print(
        f"RAM 여유 : "
        f"{available_ram_gb:.2f} GB"
    )

    if total_ram_gb < 16:

        warning(
            "시스템 RAM이 16GB 미만입니다."
        )

    # Disk
    total, used, free = (
        shutil.disk_usage(
            Path.cwd()
        )
    )

    total_gb = (
        total
        / (1024 ** 3)
    )

    free_gb = (
        free
        / (1024 ** 3)
    )

    print()
    print(
        f"현재 작업 디스크 전체 : "
        f"{total_gb:.2f} GB"
    )

    print(
        f"현재 작업 디스크 여유 : "
        f"{free_gb:.2f} GB"
    )

    if free_gb < 15:

        error(
            "디스크 여유 공간이 15GB 미만입니다."
        )

    elif free_gb < 30:

        warning(
            "디스크 여유 공간이 30GB 미만입니다."
        )

    else:

        ok(
            "디스크 여유 공간 충분"
        )


# ============================================================
# VRAM 기반 Gemma 4 E2B QLoRA 권장 설정
# ============================================================

def recommend_config(cuda_info):

    section(
        "9. Gemma 4 E2B QLoRA 권장 CONFIG"
        "예상 사용량을 기입한 것이기 때문에, 정확하지 않을 수 있습니다.유의하시길 바랍니다."
    )

    if cuda_info is None:

        print(
            "CUDA GPU가 없어 추천 설정을 생성할 수 없습니다."
        )

        return

    vram = cuda_info["gpu"]["vram"]
    bf16 = cuda_info["bf16"]

    dtype = (
        "bfloat16"
        if bf16
        else "float16"
    )

    if vram >= 24:

        config = {
            "max_seq_length": 8192,
            "batch_size": 1,
            "gradient_accumulation": 8,
            "lora_r": 32,
            "lora_alpha": 64,
        }

    elif vram >= 16:

        config = {
            "max_seq_length": 4096,
            "batch_size": 1,
            "gradient_accumulation": 8,
            "lora_r": 16,
            "lora_alpha": 32,
        }

    elif vram >= 12:

        config = {
            "max_seq_length": 2048,
            "batch_size": 1,
            "gradient_accumulation": 16,
            "lora_r": 16,
            "lora_alpha": 32,
        }

    elif vram >= 8:

        config = {
            "max_seq_length": 1024,
            "batch_size": 1,
            "gradient_accumulation": 16,
            "lora_r": 8,
            "lora_alpha": 16,
        }

        warning(
            "VRAM 8~12GB 환경입니다. "
            "OOM 발생 가능성이 있으므로 context를 낮게 유지하십시오."
        )

    else:

        error(
            "VRAM 8GB 미만: "
            "Gemma 4 E2B QLoRA 표준 구성 비추천"
        )

        return

    print(
        f"""
model:
  Gemma 4 E2B-it

quantization:
  load_in_4bit: true
  quant_type: nf4
  double_quant: true
  compute_dtype: {dtype}

training:
  max_seq_length: {config['max_seq_length']}
  per_device_train_batch_size: {config['batch_size']}
  gradient_accumulation_steps: {config['gradient_accumulation']}
  gradient_checkpointing: true

lora:
  target_modules: all-linear
  r: {config['lora_r']}
  alpha: {config['lora_alpha']}
  dropout: 0.05

optimizer:
  paged_adamw_8bit
"""
    )

    print(
        "※ 위 값은 초기 권장값이며 "
        "실제 학습 시 VRAM 실측 후 조정하십시오."
    )


# ============================================================
# 최종 판결
# ============================================================

def final_result():

    section("10. 최종 판결")

    if ERRORS:

        print("RESULT : FAIL")
        print()

        print(
            f"오류 {len(ERRORS)}개 발견"
        )

        for item in ERRORS:

            print(
                f"  - {item}"
            )

        if FIX_COMMANDS:

            print()
            print(
                "권장 수정 명령:"
            )

            for command in FIX_COMMANDS:

                print()
                print(command)

        print()
        print(
            "환경 수정 후 CHECK_ENV.py를 다시 실행하십시오."
        )

        return False

    if WARNINGS:

        print("RESULT : WARNING")
        print()

        print(
            f"경고 {len(WARNINGS)}개"
        )

        for item in WARNINGS:

            print(
                f"  - {item}"
            )

        print()
        print(
            "학습은 가능할 수 있으나 "
            "위 항목을 확인하는 것을 권장합니다."
        )

        return True

    print("RESULT : PASS")
    print()

    print(
        "Gemma 4 E2B QLoRA 학습 환경이 "
        "프로젝트 표준과 일치합니다."
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "============================================================"
    )
    print(
        "                     CHECK_ENV"
    )
    print(
        "        Gemma 4 E2B QLoRA Environment Checker"
    )
    print(
        "============================================================"
    )

    # Python 자체가 다르면 즉시 종료
    check_python()

    # pip 확인
    ensure_pip()

    # 라이브러리 존재 확인 / 누락 시 설치
    check_and_install_packages()

    # 실제 import
    import_packages()

    # 실제 로드된 버전 확인
    check_runtime_versions()

    # GPU / CUDA
    cuda_info = check_cuda()

    # bitsandbytes 실연산
    check_bitsandbytes()

    # RAM / 디스크
    check_system_resources()

    # VRAM 기반 설정 추천
    recommend_config(
        cuda_info
    )

    # 최종 판정
    success = final_result()

    print()

    if success:

        sys.exit(0)

    sys.exit(1)


if __name__ == "__main__":
    main()