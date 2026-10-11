"""Confirm the documented directory structure against the public S3 bucket.

This is intentionally a live integration test. It requires internet access, but
does not require AWS credentials or third-party Python packages.
"""

import os
import random
import time
import unittest
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree


S3_ENDPOINT = "https://mirrulations.s3.amazonaws.com/"
S3_NAMESPACE = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
SOURCE_DATA_PREFIX = "raw-data/"
MAX_CANDIDATES = 100
MAX_CANDIDATES_PER_AGENCY = 3
REQUEST_ATTEMPTS = 3


def list_s3_prefix(*, prefix="", delimiter=None, max_keys=1000):
    """Return immediate prefixes and objects from an unsigned S3 request."""
    query_parameters = {
        "list-type": "2",
        "prefix": prefix,
        "max-keys": str(max_keys),
    }
    if delimiter is not None:
        query_parameters["delimiter"] = delimiter

    request_url = S3_ENDPOINT + "?" + urllib.parse.urlencode(query_parameters)
    request = urllib.request.Request(
        request_url,
        headers={"User-Agent": "mirrulations-regulation-data-structure-test"},
    )
    for request_attempt in range(1, REQUEST_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_xml = ElementTree.fromstring(response.read())
            break
        except (ConnectionError, TimeoutError, urllib.error.URLError):
            if request_attempt == REQUEST_ATTEMPTS:
                raise
            time.sleep(request_attempt)

    prefixes = [
        prefix_element.text
        for prefix_element in response_xml.findall(
            "s3:CommonPrefixes/s3:Prefix", S3_NAMESPACE
        )
    ]
    object_keys = [
        content_element.find("s3:Key", S3_NAMESPACE).text
        for content_element in response_xml.findall("s3:Contents", S3_NAMESPACE)
    ]
    return prefixes, object_keys, request_url


class LiveS3StructureTest(unittest.TestCase):
    """Validate a randomly selected regulation in the live S3 bucket."""

    def test_random_regulation_matches_documented_structure(self):
        random_seed = os.getenv("MIRRULATIONS_TEST_SEED")
        random_generator = random.Random(random_seed)

        root_prefixes, _, root_request_url = list_s3_prefix(delimiter="/")
        self.assertIn(
            SOURCE_DATA_PREFIX,
            root_prefixes,
            f"The source data prefix was absent. Request: {root_request_url}",
        )

        agency_prefixes, _, agency_request_url = list_s3_prefix(
            prefix=SOURCE_DATA_PREFIX, delimiter="/"
        )
        self.assertTrue(
            agency_prefixes,
            f"No agency prefixes were found. Request: {agency_request_url}",
        )

        # Try agencies and dockets in random order because newly created or
        # partially ingested records may not yet contain the canonical docket
        # JSON. The selected regulation must be complete enough to exercise
        # the documented hierarchy.
        random_generator.shuffle(agency_prefixes)
        selected_docket_prefix = None
        docket_children = []
        text_children = []
        docket_request_url = None
        text_request_url = None
        inspected_candidate_count = 0
        for agency_prefix in agency_prefixes:
            docket_prefixes, _, _ = list_s3_prefix(
                prefix=agency_prefix, delimiter="/"
            )
            random_generator.shuffle(docket_prefixes)
            for candidate_docket_prefix in docket_prefixes[:MAX_CANDIDATES_PER_AGENCY]:
                inspected_candidate_count += 1
                if inspected_candidate_count > MAX_CANDIDATES:
                    break
                candidate_docket_id = candidate_docket_prefix.rstrip("/").rsplit(
                    "/", 1
                )[-1]
                candidate_docket_children, _, candidate_docket_request_url = (
                    list_s3_prefix(prefix=candidate_docket_prefix, delimiter="/")
                )
                candidate_text_prefix = (
                    f"{candidate_docket_prefix}text-{candidate_docket_id}/"
                )
                if candidate_text_prefix not in candidate_docket_children:
                    continue
                candidate_text_children, _, candidate_text_request_url = (
                    list_s3_prefix(prefix=candidate_text_prefix, delimiter="/")
                )
                if f"{candidate_text_prefix}docket/" not in candidate_text_children:
                    continue

                selected_docket_prefix = candidate_docket_prefix
                docket_children = candidate_docket_children
                text_children = candidate_text_children
                docket_request_url = candidate_docket_request_url
                text_request_url = candidate_text_request_url
                break
            if selected_docket_prefix is not None:
                break
            if inspected_candidate_count > MAX_CANDIDATES:
                break

        self.assertIsNotNone(
            selected_docket_prefix,
            f"No regulation with a docket JSON was found among "
            f"{MAX_CANDIDATES} randomized candidates below agencies returned by "
            f"{agency_request_url}",
        )

        docket_id = selected_docket_prefix.rstrip("/").rsplit("/", 1)[-1]

        binary_prefix = f"{selected_docket_prefix}binary-{docket_id}/"
        text_prefix = f"{selected_docket_prefix}text-{docket_id}/"
        expected_docket_children = {binary_prefix, text_prefix}
        self.assertTrue(
            set(docket_children).issubset(expected_docket_children),
            f"Unexpected children for {selected_docket_prefix}. "
            f"Request: {docket_request_url}",
        )
        self.assertIn(
            text_prefix,
            docket_children,
            f"The required text directory was absent for {selected_docket_prefix}. "
            f"Request: {docket_request_url}",
        )

        # S3 has no real directories, so regulations without attachments do
        # not have a binary prefix. Validate its children whenever it exists.
        if binary_prefix in docket_children:
            binary_children, _, binary_request_url = list_s3_prefix(
                prefix=binary_prefix, delimiter="/"
            )
            expected_binary_children = {
                f"{binary_prefix}comments_attachments/",
                f"{binary_prefix}documents_attachments/",
            }
            self.assertTrue(
                set(binary_children).issubset(expected_binary_children),
                f"Unexpected binary directories below {binary_prefix}: "
                f"{binary_children}. Request: {binary_request_url}",
            )

        expected_text_children = {
            f"{text_prefix}comments/",
            f"{text_prefix}comments_extracted_text/",
            f"{text_prefix}docket/",
            f"{text_prefix}documents/",
            f"{text_prefix}documents_extracted_text/",
        }
        self.assertTrue(
            set(text_children).issubset(expected_text_children),
            f"Unexpected text directories below {text_prefix}. "
            f"Request: {text_request_url}",
        )
        self.assertIn(
            f"{text_prefix}docket/",
            text_children,
            f"The required docket directory was absent below {text_prefix}. "
            f"Request: {text_request_url}",
        )

        _, docket_object_keys, docket_objects_request_url = list_s3_prefix(
            prefix=f"{text_prefix}docket/"
        )
        expected_docket_key = f"{text_prefix}docket/{docket_id}.json"
        self.assertIn(
            expected_docket_key,
            docket_object_keys,
            f"The docket JSON was absent. Request: {docket_objects_request_url}",
        )

        print(
            "Confirmed live Mirrulations structure for randomly selected "
            f"s3://mirrulations/{selected_docket_prefix}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)