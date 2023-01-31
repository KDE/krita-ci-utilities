#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2023 KDE e.V.
# SPDX-FileContributor: Ingo Klöcker <dev@ingo-kloecker.de>
#
# SPDX-License-Identifier: BSD-2-Clause

# See README.md for usage information.

import json
import logging
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from zipfile import ZipFile

try:
    import requests
    from azure.storage.blob import BlobClient
    from markdownify import markdownify
    from microstore.MicrosoftStoreClient import MicrosoftStoreClient
except ImportError as e:
    print("Error: %s" % e, file=sys.stderr)
    print("Please install the requirements (see requirements.txt)!")
    sys.exit(1)


class Error(Exception):
    pass


logger = logging.getLogger(__name__)

# Maps AppStream language ID to Microsoft language ID
appstream_to_microsoft_language = {
    "en": "en-us",  # the apps.kde.org appdata is actually a bit mangled the real key would be C not 'en'
    "sr": "sr-cyrl",
    "sr-la": "sr-Latn",  # preserve capital letter (by default we downcase)
    "ca-va": "ca-es-valencia",
    "az": "az-arab",
}
# Languages that are supported by Microsoft Store
# (https://docs.microsoft.com/en-us/windows/uwp/publish/supported-languages):
microsoft_languages = [
    # Arabic
    "ar",
    "ar-sa",
    "ar-ae",
    "ar-bh",
    "ar-dz",
    "ar-eg",
    "ar-iq",
    "ar-jo",
    "ar-kw",
    "ar-lb",
    "ar-ly",
    "ar-ma",
    "ar-om",
    "ar-qa",
    "ar-sy",
    "ar-tn",
    "ar-ye",
    # Afrikaans
    "af",
    "af-za",
    # Albanian
    "sq",
    "sq-al",
    # Amharic
    "am",
    "am-et",
    # Armenian
    "hy",
    "hy-am",
    # Assamese
    "as",
    "as-in",
    # Azerbaijani
    "az-arab",
    "az-arab-az",
    "az-cyrl",
    "az-cyrl-az",
    "az-latn",
    "az-latn-az",
    # Basque (Basque)
    "eu",
    "eu-es",
    # Belarusian
    "be",
    "be-by",
    # Bangla
    "bn",
    "bn-bd",
    "bn-in",
    # Bosnian
    "bs",
    "bs-cyrl",
    "bs-cyrl-ba",
    "bs-latn",
    "bs-latn-ba",
    # Bulgarian
    "bg",
    "bg-bg",
    # Catalan
    "ca",
    "ca-es",
    "ca-es-valencia",
    # Cherokee
    "chr-cher",
    "chr-cher-us",
    "chr-latn",
    # Chinese (Simplified)
    "zh-Hans",
    "zh-cn",
    "zh-hans-cn",
    "zh-sg",
    "zh-hans-sg",
    # Chinese (Traditional)
    "zh-Hant",
    "zh-hk",
    "zh-mo",
    "zh-tw",
    "zh-hant-hk",
    "zh-hant-mo",
    "zh-hant-tw",
    # Croatian
    "hr",
    "hr-hr",
    "hr-ba",
    # Czech
    "cs",
    "cs-cz",
    # Danish
    "da",
    "da-dk",
    # Dari
    "prs",
    "prs-af",
    "prs-arab",
    # Dutch
    "nl",
    "nl-nl",
    "nl-be",
    # English
    "en",
    "en-au",
    "en-ca",
    "en-gb",
    "en-ie",
    "en-in",
    "en-nz",
    "en-sg",
    "en-us",
    "en-za",
    "en-bz",
    "en-hk",
    "en-id",
    "en-jm",
    "en-kz",
    "en-mt",
    "en-my",
    "en-ph",
    "en-pk",
    "en-tt",
    "en-vn",
    "en-zw",
    "en-053",
    "en-021",
    "en-029",
    "en-011",
    "en-018",
    "en-014",
    # Estonian
    "et",
    "et-ee",
    # Filipino
    "fil",
    "fil-latn",
    "fil-ph",
    # Finnish
    "fi",
    "fi-fi",
    # French
    "fr",
    "fr-be ",
    "fr-ca ",
    "fr-ch ",
    "fr-fr ",
    "fr-lu",
    "fr-015",
    "fr-cd",
    "fr-ci",
    "fr-cm",
    "fr-ht",
    "fr-ma",
    "fr-mc",
    "fr-ml",
    "fr-re",
    "frc-latn",
    "frp-latn",
    "fr-155",
    "fr-029",
    "fr-021",
    "fr-011",
    # Galician
    "gl",
    "gl-es",
    # Georgian
    "ka",
    "ka-ge",
    # German
    "de",
    "de-at",
    "de-ch",
    "de-de",
    "de-lu",
    "de-li",
    # Greek
    "el",
    "el-gr",
    # Gujarati
    "gu",
    "gu-in",
    # Hausa
    "ha",
    "ha-latn",
    "ha-latn-ng",
    # Hebrew
    "he",
    "he-il",
    # Hindi
    "hi",
    "hi-in",
    # Hungarian
    "hu",
    "hu-hu",
    # Icelandic
    "is",
    "is-is",
    # Igbo
    "ig-latn",
    "ig-ng",
    # Indonesian
    "id",
    "id-id",
    # Inuktitut (Latin)
    "iu-cans",
    "iu-latn",
    "iu-latn-ca",
    # Irish
    "ga",
    "ga-ie",
    # isiXhosa
    "xh",
    "xh-za",
    # isiZulu
    "zu",
    "zu-za",
    # Italian
    "it",
    "it-it",
    "it-ch",
    # Japanese
    "ja ",
    "ja-jp",
    # Kannada
    "kn",
    "kn-in",
    # Kazakh
    "kk",
    "kk-kz",
    # Khmer
    "km",
    "km-kh",
    # K'iche',
    "quc-latn",
    "qut-gt",
    "qut-latn",
    # Kinyarwanda
    "rw",
    "rw-rw",
    # KiSwahili
    "sw",
    "sw-ke",
    # Konkani
    "kok",
    "kok-in",
    # Korean
    "ko",
    "ko-kr",
    # Kurdish
    "ku-arab",
    "ku-arab-iq",
    # Kyrgyz
    "ky-kg",
    "ky-cyrl",
    # Lao
    "lo",
    "lo-la",
    # Latvian
    "lv",
    "lv-lv",
    # Lithuanian
    "lt",
    "lt-lt",
    # Luxembourgish
    "lb",
    "lb-lu",
    # Macedonian
    "mk",
    "mk-mk",
    # Malay
    "ms",
    "ms-bn",
    "ms-my",
    # Malayalam
    "ml",
    "ml-in",
    # Maltese
    "mt",
    "mt-mt",
    # Maori
    "mi",
    "mi-latn",
    "mi-nz",
    # Marathi
    "mr",
    "mr-in",
    # Mongolian (Cyrillic)
    "mn-cyrl",
    "mn-mong",
    "mn-mn",
    "mn-phag",
    # Nepali
    "ne",
    "ne-np",
    # Norwegian
    "nb",
    "nb-no",
    "nn",
    "nn-no",
    "no",
    "no-no",
    # Odia
    "or",
    "or-in",
    # Persian
    "fa",
    "fa-ir",
    # Polish
    "pl",
    "pl-pl",
    # Portuguese (Brazil)
    "pt-br",
    # Portuguese (Portugal)
    "pt",
    "pt-pt",
    # Punjabi
    "pa",
    "pa-arab",
    "pa-arab-pk",
    "pa-deva",
    "pa-in",
    # Quechua
    "quz",
    "quz-bo",
    "quz-ec",
    "quz-pe",
    # Romanian
    "ro",
    "ro-ro",
    # Russian
    "ru ",
    "ru-ru",
    # Scottish Gaelic
    "gd-gb",
    "gd-latn",
    # Serbian (Latin)
    "sr-Latn",
    "sr-latn-cs",
    "sr",
    "sr-latn-ba",
    "sr-latn-me",
    "sr-latn-rs",
    # Serbian (Cyrillic)
    "sr-cyrl",
    "sr-cyrl-ba",
    "sr-cyrl-cs",
    "sr-cyrl-me",
    "sr-cyrl-rs",
    # Sesotho sa Leboa
    "nso",
    "nso-za",
    # Setswana
    "tn",
    "tn-bw",
    "tn-za",
    # Sindhi
    "sd-arab",
    "sd-arab-pk",
    "sd-deva",
    # Sinhala
    "si",
    "si-lk",
    # Slovak
    "sk",
    "sk-sk",
    # Slovenian
    "sl",
    "sl-si",
    # Spanish
    "es",
    "es-cl",
    "es-co",
    "es-es",
    "es-mx",
    "es-ar",
    "es-bo",
    "es-cr",
    "es-do",
    "es-ec",
    "es-gt",
    "es-hn",
    "es-ni",
    "es-pa",
    "es-pe",
    "es-pr",
    "es-py",
    "es-sv",
    "es-us",
    "es-uy",
    "es-ve",
    "es-019",
    "es-419",
    # Swedish
    "sv",
    "sv-se",
    "sv-fi",
    # Tajik (Cyrillic)
    "tg-arab",
    "tg-cyrl",
    "tg-cyrl-tj",
    "tg-latn",
    # Tamil
    "ta",
    "ta-in",
    # Tatar
    "tt-arab",
    "tt-cyrl",
    "tt-latn",
    "tt-ru",
    # Telugu
    "te",
    "te-in",
    # Thai
    "th",
    "th-th",
    # Tigrinya
    "ti",
    "ti-et",
    # Turkish
    "tr",
    "tr-tr",
    # Turkmen
    "tk-cyrl",
    "tk-latn",
    "tk-tm",
    "tk-latn-tr",
    "tk-cyrl-tr",
    # Ukrainian
    "uk",
    "uk-ua",
    # Urdu
    "ur",
    "ur-pk",
    # Uyghur
    "ug-arab",
    "ug-cn",
    "ug-cyrl",
    "ug-latn",
    # Uzbek (Latin)
    "uz",
    "uz-cyrl",
    "uz-latn",
    "uz-latn-uz",
    # Vietnamese
    "vi",
    "vi-vn",
    # Welsh
    "cy",
    "cy-gb",
    # Wolof
    "wo",
    "wo-sn",
    # Yoruba
    "yo-latn",
    "yo-ng",
]
# Languages supported by KDE that are not supported by Microsoft:
# * ast (Asturian), ia (Interlingua), ie (Interlingue) are not supported by Microsoft
# * some SR variants are not a thing outside the KDE bubble
# * x-test


def parseCommandLine():
    import argparse

    parser = argparse.ArgumentParser(description="Client for submitting KDE apps to the Microsoft Store")

    # debug options
    parser.add_argument("-v", "--verbose", action="count", default=0, help="increase the verbosity")
    parser.add_argument(
        "--dry-run", dest="dryRun", action="store_true", help="perform a trial run without submitting any changes"
    )
    parser.add_argument(
        "--debug-authorization",
        type=int,
        default=0,
        dest="debugAuth",
        metavar="LEVEL",
        help="debug level for authorization (1 or 2)",
    )
    parser.add_argument(
        "--debug-api-calls",
        type=int,
        default=0,
        dest="debugApi",
        metavar="LEVEL",
        help="debug level for API calls (1 or 2)",
    )

    parser.add_argument(
        "--tenant-id",
        dest="tenantId",
        help="the tenant ID; required; can also be set via MSSTORE_TENANT_ID environment variable",
    )
    parser.add_argument(
        "--client-id",
        dest="clientId",
        help="the client ID; required; can also be set via MSSTORE_CLIENT_ID environment variable",
    )

    parser.add_argument(
        "--store-id",
        dest="storeId",
        help="the Microsoft Store ID of the app; if not given, it is retrieved from the AppStream data",
    )
    parser.add_argument(
        "--keep",
        default="",
        dest="keep",
        help="comma-separated list of attributes to keep when updating the submission data from the AppStream data",
    )

    parser.add_argument("appstreamId", help="the AppStream ID of the application")
    parser.add_argument("appxuploadFile", help="the .appxupload file to submit")

    options = parser.parse_args()
    options.keep = [s.lower() for s in options.keep.split(",") if s]
    return options


def setUpLogging(options):
    logging.basicConfig(format="%(asctime)s %(name)s %(message)s", level=logging.WARNING)
    logger.setLevel(max(logging.DEBUG, logging.WARNING - 10 * options.verbose))
    msstoreLogger = logging.getLogger("msstore")
    msstoreLogger.setLevel(max(logging.DEBUG, logging.WARNING - 10 * options.verbose))
    authLogger = logging.getLogger("msstore.auth")
    authLogger.setLevel(max(logging.DEBUG, logging.WARNING - 10 * options.debugAuth))
    apiLogger = logging.getLogger("msstore.api")
    apiLogger.setLevel(max(logging.DEBUG, logging.WARNING - 10 * options.debugApi))


def getAppStreamData(appstreamId):
    r = requests.get(f"https://apps.kde.org/appdata/{appstreamId}.json")
    r.raise_for_status()
    return r.json()


def createListing(title):
    return {
        "baseListing": {
            "copyrightAndTrademarkInfo": "",
            "keywords": [],
            "licenseTerms": "",
            "privacyPolicy": "",
            "supportContact": "",
            "websiteUrl": "",
            "description": "",
            "features": [],
            "releaseNotes": "",
            "images": [],
            "recommendedHardware": [],
            "minimumHardware": [],
            "title": title,
            "shortDescription": "",
            "shortTitle": "",
            "sortTitle": "",
            "voiceTitle": "",
            "devStudio": "",
        }
    }


def downloadFile(url, downloadPath):
    localPath = downloadPath / Path(urlparse(url).path).name
    if localPath.exists():
        logger.debug(f"File {downloadPath} already exists. Skipping download.")
        return localPath

    logger.debug(f"Downloading {url}")
    r = requests.get(url)
    if not r.ok:
        logger.warning(f"Failed to download {url}")
        return
    logger.debug(f"Writing file to {localPath}")
    os.makedirs(downloadPath, exist_ok=True)
    with open(localPath, "wb") as f:
        f.write(r.content)
    return localPath


def reformatDescription(description):
    description = description.strip()
    if description.startswith("<"):
        # convert any linebreaks in the HTML code to spaces (linebreaks are
        # meaningless in HTML, but markdownify does not touch them)
        description = description.replace("\n", " ")
        # convert HTML description to Markdown (Microsoft Store only supports
        # plain text, but some Markdown looks nicer)
        description = markdownify(description, heading_style="UNDERLINED").strip()
        # remove leading (and trailing) whitespace from all lines
        description = "\n".join(line.strip() for line in description.split("\n"))
    return description


def updateBaseListingForLanguage(lang, storeLang, baseListing, defaultBaseListing, appstreamData, downloadPath, keep):
    # update description for listing
    storeDescription = baseListing.get("description", "")
    if "description" not in keep or not storeDescription:
        description = appstreamData.get("Description", {}).get(lang, "")
        if not description:
            logger.debug(f"No description for {lang}. Skipping update of listing for language.")
            return
        baseListing["description"] = reformatDescription(description)

    # copyrightAndTrademarkInfo - AppStream does not provide this

    # update keywords for listing
    if "keywords" not in keep or not baseListing["keywords"]:
        baseListing["keywords"] = appstreamData.get("Keywords", {}).get(lang, [])

    # update licenseTerms for listing
    if "licenseterms" not in keep or not baseListing["licenseTerms"]:
        baseListing["licenseTerms"] = appstreamData.get("ProjectLicense", "")

    # privacyPolicy - This value is obsolete. The privacy policy URL must be set in Partner Center.

    # update supportContact for listing
    if "supportcontact" not in keep or not baseListing["supportContact"]:
        baseListing["supportContact"] = appstreamData.get("Url", {}).get("contact", "")

    # update websiteUrl for listing
    if "websiteurl" not in keep or not baseListing["websiteUrl"]:
        baseListing["websiteUrl"] = appstreamData.get("Url", {}).get("homepage", "")

    # features - AppStream does not provide a list of features (https://github.com/ximion/appstream/issues/388)

    # update releaseNotes for listing
    if "releasenotes" not in keep or not baseListing["releaseNotes"]:
        releases = appstreamData.get("Releases")
        if releases:  # not None and not empty
            releaseNotes = releases[0].get("description", {}).get(lang, "") or defaultBaseListing["releaseNotes"]
            baseListing["releaseNotes"] = releaseNotes
        else:
            baseListing["releaseNotes"] = ""

    # update images for listing
    if "images" not in keep or not baseListing["images"]:
        newScreenshots = []
        for screenshot in appstreamData.get("Screenshots", []):
            if not screenshot.get("default", False):
                continue
            url = screenshot.get("source-image", {}).get("url")
            imagePath = downloadFile(url, downloadPath / "images")
            if imagePath is not None:
                description = screenshot.get("caption", {}).get(lang, "")
                # assume screenshot for mobile if image filename contains 'mobile'
                imageType = "MobileScreenshot" if "mobile" in imagePath.name else "Screenshot"
                newScreenshots.append(
                    {
                        "fileName": "images/" + imagePath.name,
                        "fileStatus": "PendingUpload",
                        "description": description,
                        "imageType": imageType,
                    }
                )
        if newScreenshots:
            # replace old screenshots with new ones
            baseListing["images"] = [
                image for image in baseListing["images"] if not image["imageType"].endswith("Screenshot")
            ]
            baseListing["images"].extend(newScreenshots)

    # recommendedHardware, minimumHardware - AppStream does not provide these

    # title - title must be a reserved name; keep what's there

    # update shortDescription for listing (only used for games)
    if "shortdescription" not in keep or not baseListing["shortDescription"]:
        baseListing["shortDescription"] = appstreamData.get("Summary", {}).get(lang, "")

    # shortTitle, sortTitle, voiceTitle - AppStream does not provide these

    # update devStudio for listing
    if "devstudio" not in keep or not baseListing["devStudio"]:
        baseListing["devStudio"] = (
            appstreamData.get("DeveloperName", {}).get(lang, "") or defaultBaseListing["devStudio"]
        )

    logger.debug(f"Listing for {storeLang}: %s", json.dumps(baseListing))
    return baseListing


def updateSubmissionWithAppStreamData(submissionData, appstreamData, downloadPath, keep, title):
    listings = submissionData["listings"]
    defaultBaseListing = listings["en-us"]["baseListing"]

    if keep:
        logger.debug("Keeping the following values of the existing listings: %s", ", ".join(keep))

    # first update the (base) listing for en/en-us (the default listing)
    updateBaseListingForLanguage(
        "en", "en-us", defaultBaseListing, defaultBaseListing, appstreamData, downloadPath, keep
    )

    for lang in appstreamData["Name"]:
        if lang == "en":
            continue
        storeLang = appstream_to_microsoft_language.get(lang, lang)
        if storeLang not in microsoft_languages:
            logger.debug(f"Skipping language {lang} that is not supported by the Microsoft Store")
            continue

        listing = listings.get(storeLang)
        if listing is None:
            listing = createListing(title)
        baseListing = listing["baseListing"]
        updatedBaseListing = updateBaseListingForLanguage(
            lang, storeLang, baseListing, defaultBaseListing, appstreamData, downloadPath, keep
        )
        # we keep existing listings even if updateBaseListingForLanguage doesn't like them
        if updatedBaseListing is not None:
            listings[storeLang] = listing

    return submissionData


def uploadPackagesFiles(zipFilePath, fileUploadUrl):
    logger.debug(f"Uploading {zipFilePath} to {fileUploadUrl}")
    blobClient = BlobClient.from_blob_url(fileUploadUrl)
    with open(zipFilePath, "rb") as data:
        result = blobClient.upload_blob(data, blob_type="BlockBlob")
        logger.debug("Upload result: %s", result)


def submitApp(client, *, appstreamId, appxuploadFile, storeId, keep, dryRun, **kwargs):
    if not os.path.isfile(appxuploadFile):
        raise Error(f"File not found: {appxuploadFile}")

    if dryRun:
        logger.info("Running in dry-run mode")

    # fetch AppStream metadata of the app
    logger.info(f"Fetching AppStream metadata for {appstreamId}")
    appstreamData = getAppStreamData(appstreamId)
    if not storeId:
        # get the Store ID of the app from the AppStream data
        storeUrl = appstreamData.get("Custom", {}).get("KDE::windows_store")
        if storeUrl is None:
            raise Error("No KDE::windows_store entry found in AppStream data.")
        storeId = os.path.basename(urlparse(storeUrl).path)
    logger.debug(f"Using Store ID {storeId}")

    # get app data
    logger.info("Retrieving information about the app from the Microsoft Store")
    appData = client.getAppData(storeId)

    lastSubmissionId = appData.get("lastPublishedApplicationSubmission", {}).get("id")
    if not lastSubmissionId:
        raise Error("The first submission needs to be done manually in the Microsoft Partner Center.")

    # delete existing pending submission
    pendingSubmissionId = appData.get("pendingApplicationSubmission", {}).get("id")
    if pendingSubmissionId:  # not None and not empty
        logger.info("Deleting existing pending submission")
        if not dryRun:
            client.deleteSubmission(storeId, pendingSubmissionId)

    # create a new submission (as copy of the last submission)
    logger.info("Creating new submission")
    if not dryRun:
        submissionData = client.createSubmission(storeId)
    else:
        submissionData = client.getSubmission(storeId, lastSubmissionId)
        submissionData["id"] = int(submissionData["id"]) + 1
        submissionData["fileUploadUrl"] = "https://localhost"
    submissionId = submissionData["id"]
    logger.debug(f"submission ID: {submissionId}")

    # remove some entries from the submission data
    fileUploadUrl = submissionData["fileUploadUrl"]
    logger.debug(f"fileUploadUrl: {fileUploadUrl}")
    del submissionData["fileUploadUrl"]  # remove fileUploadUrl
    # remove deprecated "pricing.sales" entry
    if "pricing" in submissionData and "sales" in submissionData["pricing"]:
        del submissionData["pricing"]["sales"]

    with TemporaryDirectory() as tmpdirname:
        tempPath = Path(tmpdirname)
        # set data for new submission
        submissionData = updateSubmissionWithAppStreamData(
            submissionData, appstreamData, tempPath, keep, title=appData["primaryName"]
        )
        # add information about the app package (if it has not yet been uploaded)
        appPackageName = os.path.basename(appxuploadFile)
        if any(
            p["fileName"] == appPackageName and p["fileStatus"] == "Uploaded"
            for p in submissionData["applicationPackages"]
        ):
            # the app package has already been uploaded
            logger.info(f"{appPackageName} has already been uploaded")
            appPackageName = None
        else:
            logger.info(f"Adding {appPackageName} to list of application packages")
            submissionData["applicationPackages"].append(
                {
                    "fileName": appPackageName,  # relative to root of uploaded ZIP file
                    "fileStatus": "PendingUpload",
                }
            )

        # update the submission
        logger.info("Updating submission")
        if not dryRun:
            client.updateSubmission(storeId, submissionId, submissionData)
        else:
            print(f"Updated submission data:\n{json.dumps(submissionData, indent=4)}")

        # upload images and packages in a zip file
        logger.info("Packaging files to upload")
        zipFilePath = tempPath / "blob.zip"
        # we use the default ZIP_STORED compression because the files should already be fairly compressed
        with ZipFile(zipFilePath, "w") as zipFile:
            for imagePath in (tempPath / "images").iterdir():
                logger.debug(f"Adding {imagePath} to {zipFilePath}")
                zipFile.write(imagePath, arcname="images/" + imagePath.name)
            if appPackageName:
                logger.debug(f"Adding {appPackageName} to {zipFilePath}")
                zipFile.write(appxuploadFile, arcname=appPackageName)

        logger.info("Uploading packaged files")
        if not dryRun:
            uploadPackagesFiles(zipFilePath, fileUploadUrl)

    # commit the submission
    logger.info("Committing submission")
    if not dryRun:
        client.commitSubmission(storeId, submissionId, waitUntilCommitIsCompleted=True)


def main():
    options = parseCommandLine()
    setUpLogging(options)

    client = MicrosoftStoreClient(options.tenantId, options.clientId)
    submitApp(client, **vars(options))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Error as e:
        print("Error: %s" % e, file=sys.stderr)
        sys.exit(1)
