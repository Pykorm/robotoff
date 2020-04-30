from typing import Dict, List, Set

from robotoff.insights._enum import InsightType
from robotoff.models import LatentProductInsight, ProductInsight
from robotoff.products import (
    has_nutrition_image,
    is_nutrition_image,
    is_valid_image,
    get_product_store,
    DBProductStore,
)
from robotoff.utils import get_logger
from robotoff.utils.types import JSONType

logger = get_logger(__name__)

FIBER_QUALITY_FACET_NAME = "en:missing-nutrition-facts-fibers-present-on-photos"
FIBER_NUTRITION_QUALITY_FACET_NAME = (
    "en:missing-nutrition-facts-fibers-present-on-nutrition-photos"
)


def generate_quality_facets():
    generate_fiber_quality_facet()


def generate_fiber_quality_facet():
    product_store: DBProductStore = get_product_store()
    collection = product_store.collection
    added = 0
    seen_set: Set[str] = set()

    for latent_insight in (
        LatentProductInsight.select(
            LatentProductInsight.barcode, LatentProductInsight.source_image
        )
        .where(
            LatentProductInsight.type == InsightType.nutrient_mention.name,
            LatentProductInsight.data["mentions"].contains("fiber"),
            LatentProductInsight.source_image.is_null(False),
        )
        .iterator()
    ):
        barcode = latent_insight.barcode

        if barcode in seen_set:
            continue

        product = product_store.get_product(
            barcode, ["nutriments", "data_quality_tags", "images"]
        )
        nutriments = product.get("nutriments", {})
        data_quality_tags = product.get("data_quality_tags", {})
        images = product.get("images", {})

        if (
            product is None
            or not is_valid_image(images, latent_insight.source_image)
            or "fiber" in nutriments
            or "fiber_prepared" in nutriments
        ):
            continue

        facets = []

        if FIBER_QUALITY_FACET_NAME not in data_quality_tags:
            facets.append(FIBER_QUALITY_FACET_NAME)

        if (
            FIBER_NUTRITION_QUALITY_FACET_NAME not in data_quality_tags
            and is_nutrition_image(images, latent_insight.source_image)
        ):
            facets.append(FIBER_NUTRITION_QUALITY_FACET_NAME)

        if not facets:
            continue

        logger.info("Adding facets to {}: {}".format(barcode, facets))
        seen_set.add(barcode)
        added += 1
        collection.update_one(
            {"code": barcode},
            {
                "$push": {
                    "data_quality_tags": {"$each": facets},
                    "data_quality_warnings_tags": {"$each": facets},
                }
            },
        )
    logger.info("Fiber quality facets added on {} products".format(added))


def generate_nutrition_image_insights():
    logger.info("Startin nutrition image insight generation")
    product_store: DBProductStore = get_product_store()
    added = 0
    seen_set: Set[str] = set()

    latent_insight: LatentProductInsight
    for latent_insight in (
        LatentProductInsight.select()
        .where(LatentProductInsight.type == InsightType.nutrient_mention.name)
        .order_by(LatentProductInsight.source_image.desc())
        .iterator()
    ):
        barcode = latent_insight.barcode

        if barcode in seen_set:
            continue

        product = product_store.get_product(barcode, ["images"])

        if product is None:
            continue

        mentions = latent_insight.data["mentions"]
        images = product.get("images", {})

        nutrition_image_langs = find_nutrition_image_lang(mentions)

        if not has_nutrition_image(images):
            for lang in nutrition_image_langs:
                if not (
                    ProductInsight.select()
                    .where(
                        ProductInsight.type == InsightType.nutrition_image.name,
                        ProductInsight.barcode == barcode,
                        ProductInsight.value_tag == lang,
                    )
                    .count()
                ):
                    ProductInsight.create_from_latent(
                        latent_insight, type=InsightType.nutrition_image, value_tag=lang
                    )
                    added += 1

    logger.info("Added: {}".format(added))


def find_nutrition_image_lang(mentions: JSONType, min_count: int = 4) -> List[str]:
    nutrient_languages = find_nutrition_image_nutrient_languages(mentions)

    lang_count: Dict[str, int] = {}
    for _, langs in nutrient_languages.items():
        for lang, count in langs.items():
            lang_count.setdefault(lang, 0)
            lang_count[lang] += count

    return [lang for lang, count in lang_count.items() if count >= min_count]


def find_nutrition_image_nutrient_languages(
    mentions: JSONType,
) -> Dict[str, Dict[str, int]]:
    languages: Dict[str, Dict[str, int]] = {}
    for nutrient, matches in mentions.items():
        seen_lang: Set[str] = set()

        for match in matches:
            for lang in match.get("languages", []):
                if lang not in seen_lang:
                    languages.setdefault(nutrient, {})
                    nutrient_languages = languages[nutrient]
                    nutrient_languages.setdefault(lang, 0)
                    nutrient_languages[lang] += 1
                    seen_lang.add(lang)

    return languages
