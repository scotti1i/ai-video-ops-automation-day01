from video_ops.application.service import VideoOperationsService

BLENDER_BRIEF = "为每天早上赶时间的上班族推广便携榨汁杯，重点讲随行杯直接饮用，目标 25 秒，美区英文"


def _generate(service: VideoOperationsService, count: int = 10):
    return service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url="https://example.com/reference-video",
        count=count,
        producer="mock",
    )


def test_fixed_blender_script_is_traceable_shootable_and_25_seconds(
    service: VideoOperationsService,
) -> None:
    _, candidates = _generate(service, count=1)
    candidate = candidates[0]

    assert candidate.claims_used == ["随行杯直接饮用"]
    assert candidate.claims_needing_evidence == []
    assert sum(item.duration_seconds for item in candidate.shots) == 25
    assert candidate.shots[0].role == "hook"
    assert candidate.shots[0].duration_seconds <= 3
    assert sum(item.duration_seconds for item in candidate.shots[:2]) <= 6
    assert any(item.role == "proof" for item in candidate.shots)
    assert candidate.shots[-1].role == "cta"
    assert candidate.script == "\n".join(item.voiceover for item in candidate.shots)
    assert "weight loss" not in candidate.script.lower()
    assert "discount" not in candidate.script.lower()


def test_chinese_usb_c_copy_uses_chinese_pacing_with_latin_brand_tokens(
    service: VideoOperationsService,
) -> None:
    _, candidates = service.generate_batch(
        product_id="product-blender",
        brief="给通勤用户推广便携榨汁杯，重点讲 USB-C 充电，目标 25 秒",
        reference_url=None,
        count=10,
        producer="mock",
    )

    assert all(item.quality.status == "ready_to_test" for item in candidates)
    assert all("USB-C" in item.script for item in candidates)
