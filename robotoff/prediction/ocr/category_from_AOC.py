import re
from typing import List, Optional, Union


from robotoff.prediction.types import Prediction, PredictionType
from robotoff.utils import get_logger
from robotoff.taxonomy import get_taxonomy
from robotoff.off import normalizing

from .dataclass import OCRField, OCRRegex, OCRResult, get_text

logger = get_logger(__name__)


def category_taxonomisation(lang, match) -> Optional[str]:
    '''Function to match categories detected via AOP REGEX with categories
    taxonomy database. If no match is possible, we return None.'''

    unchecked_category = lang + normalizing(match.group("category"))

    checked_category = get_taxonomy("category").nodes.get(unchecked_category)

    if checked_category is not None:
        return checked_category.id

    return None


'''We must increase the scale of prediction of our REGEX
Many names of AOC products are written this way :
"AMARONE della VALPONE"
"Denominazione di Origine Controllata"
'''
AOC_REGEX = {
    "fr:": [
        OCRRegex(
            # re.compile(r"(?<=appellation\s).*(?=(\scontr[ôo]l[ée]e)|(\sprot[ée]g[ée]e))"),
            re.compile(r"(appellation)\s*(?P<category>.+)\s*(contr[ôo]l[ée]e|prot[ée]g[ée]e)"),
            field=OCRField.full_text_contiguous,
            lowercase=True,
            processing_func=category_taxonomisation,
        ),
        OCRRegex(
            re.compile(r"(?P<category>.+)\s*(appellation d'origine contr[ôo]l[ée]e|appellation d'origine prot[ée]g[ée]e)"),
            field=OCRField.full_text_contiguous,
            lowercase=True,
            processing_func=category_taxonomisation,
        ),
    ],
    "es:": [
        OCRRegex(
            re.compile(r"(?P<category>.+)(\s*denominacion de origen protegida)"),
            field=OCRField.full_text_contiguous,
            lowercase=True,
            processing_func=category_taxonomisation,
        ),
        OCRRegex(
            re.compile(r"(denominacion de origen protegida\s*)(?P<category>.+)"),
            field=OCRField.full_text_contiguous,
            lowercase=True,
            processing_func=category_taxonomisation,
        ),
    ],
    "en:": [
        OCRRegex(
            re.compile(r"(?P<category>.+)\s*(aop|dop|pdo)"),
            field=OCRField.full_text_contiguous,
            lowercase=True,
            processing_func=category_taxonomisation,
        ),
        OCRRegex(
            re.compile(r"(aop|dop|pdo)\s*(?P<category>.+)"),
            field=OCRField.full_text_contiguous,
            lowercase=True,
            processing_func=category_taxonomisation,
        ),
    ],
}


def find_category_from_AOC(content: Union[OCRResult, str]) -> List[Prediction]:

    predictions = []

    for lang, regex_list in AOC_REGEX.items():
        for ocr_regex in regex_list:
            text = get_text(content, ocr_regex)

            if not text:
                continue

            for match in ocr_regex.regex.finditer(text):

                category_value = ocr_regex.processing_func(lang, match)

                if category_value is not None:

                    predictions.append(
                        Prediction(
                            type=PredictionType.category,
                            value_tag=category_value,
                            predictor="regex",
                            data={"text": match.group(), "notify": ocr_regex.notify},
                        )
                    )
    return predictions


'''This function returns a prediction of the category of the product
by detecting an AOC syntax which allows an easy category
prediction with REGEX'''
