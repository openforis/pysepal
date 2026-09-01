"""The translator object allow developer to support translation for their application."""

import json
from pathlib import Path
from typing import List, Tuple, Union

import pandas as pd
from box import Box
from deprecated.sphinx import deprecated, versionadded


class Translator(Box):

    _protected_keys = [
        "find_target",
        "search_key",
        "sanitize",
        "_update",
        "missing_keys",
        "available_locales",
        "merge_dict",
        "delete_empty",
    ] + dir(Box)
    "keys that cannot be used as var names as they are protected for methods"

    def __init__(
        self, json_folder: Union[str, Path], target: str = "", default: str = "en"
    ) -> None:
        """Python ``Box`` of ``Box`` representing all the nested translation key, value pairs.

        It reads 2 Json files, the first one being the source language (usually English) and the second one the target language.
        It will replace in the source dictionary every key that exist in both json dictionaries. Following this procedure, every message that is not translated can still be accessed in the source language.
        To access the dictionary keys, instead of using [], you can simply use key name as in an object ex: translator.first_key.secondary_key.
        There are no depth limits, just respect the snake_case convention when naming your keys in the .json files.
        5 internal keys are created upon initialization (there name cannot be used as keys in the translation message):

        -   (str) _default : the default locale of the translator
        -   (str) _targeted : the initially requested language. Use to display debug information to the user agent
        -   (str) _target : the target locale of the translator
        -   (bool) _match : if the target language match the one requested one by user, used to trigger information in appBar
        -   (str) _folder : the path to the l10n folder

        Args:
            json_folder: The folder where the dictionaries are stored
            target: The language code (IETF BCP 47) of the target lang (it should be the same as the target dictionary); when empty, English is used.
            default: The language code (IETF BCP 47) of the source lang. default to "en" (it should be the same as the source dictionary)
        """
        # the name of the 5 variables that cannot be used as init keys
        FORBIDDEN_KEYS = ["_folder", "_default", "_target", "_targeted", "_match"]

        # init the box with the folder
        folder = Path(json_folder)

        # reading the default dict
        default_dict = self.merge_dict(folder / default)

        # create a dictionary in the target language
        targeted, target = self.find_target(folder, target)
        target = target or default
        target_dict = self.merge_dict(folder / target)

        # evaluate the matching of requested and obtained values
        match = targeted == target

        # create the composite dictionary
        ms_dict = self._update(default_dict, target_dict)

        # check if forbidden keys are being used
        # this will raise an error if any
        [self.search_key(ms_dict, k) for k in FORBIDDEN_KEYS + self._protected_keys]

        # # unpack the json as a simple namespace
        ms_json = json.dumps(ms_dict)
        ms_boxes = json.loads(ms_json, object_hook=lambda d: Box(**d, frozen_box=True))

        private_keys = {
            "_folder": str(folder),
            "_default": default,
            "_targeted": targeted,
            "_target": target,
            "_match": match,
        }

        # the final box is not frozen
        # waiting for an answer here: https://github.com/cdgriffith/Box/issues/223
        # it the meantime it's easy to call the translator using a frozen_box argument
        super(Box, self).__init__(**private_keys, **ms_boxes)

    @versionadded(version="2.7.0")
    @staticmethod
    def find_target(folder: Path, target: str = "") -> Tuple[str, str]:
        """find the target language in the available language folder.

        given a folder and a target lang, this function returns the closest language available in the folder
        If nothing is found falling back to any working subvariety and return None if it doesn't exist

        Args:
            folder: the folder where the languages dictionaries are stored
            target: the target lang in IETF BCP 47; when empty, English is used

        Returns:
            the targeted language code, the closest lang in IETF BCP 47
        """
        # init lang
        lang = ""

        # No target: English, deterministically. This used to read
        # ~/.sepal-ui-config, so a machine-global file decided the language of
        # every connection in a multi-user container.
        if target == "":
            return ("", "en")

        # first scenario the target is available
        if (folder / target).is_dir():
            lang = target
        # second scenario the "main lang" is set
        elif (folder / target[:2]).is_dir():
            lang = target[:2]
        # third scenario we search for any closely related language
        else:
            try:
                f = next(f for f in folder.glob(f"{target[:2]}-*") if f.is_dir())
                lang = f.stem
            except StopIteration:
                pass

        return (target, lang)

    @classmethod
    def search_key(cls, d: dict, key: str) -> None:
        """Search a specific key in the d dictionary and raise an error if found.

        Args:
            d: the dictionary to study
            key: the key to look for
        """
        if key in d:
            msg = f"You cannot use the key {key} in your translation dictionary"
            raise Exception(msg)

        for v in d.values():
            if isinstance(v, dict):
                cls.search_key(v, key)

    @classmethod
    def sanitize(cls, d: Union[dict, list]) -> dict:
        """Identify numbered dictionaries embedded in the dict and transform them into lists.

        This function is an helper to prevent deprecation after the introduction of pontoon for translation.
        The user is now force to use keys even for numbered lists. SimpleNamespace doesn't support integer indexing
        so this function will transform back this "numbered" dictionary (with integer keys) into lists.

        Args:
            d: the dictionary to sanitize

        Returns:
            the sanitized dictionary
        """
        ms = d.copy()

        # create generator based on input type
        if isinstance(ms, dict):
            gen = ms.items()
        elif isinstance(ms, list):
            gen = enumerate(ms)

        # loop into the keys of the dict modify them
        for k, v in gen:
            if isinstance(v, dict):
                tmp = v
                if len(tmp) and all([k.isnumeric() for k in tmp]):
                    tmp = list(tmp.values())
                ms[k] = cls.sanitize(tmp)
            else:
                ms[k] = v

        return ms

    def _update(self, d: dict, u: dict) -> dict:
        """Update the fallback dictionnaire (d) values with the keys that exist in the target (u) dictionnaire.

        Args:
            d: The fallback dictionary
            u: the target dctionnary

        Returns:
            The updated dictionnay
        """
        ms = d.copy()

        for k, v in d.items():
            if isinstance(v, dict):
                ms[k] = self._update(v, u.get(k, {}))
            else:
                ms[k] = u.get(k, v)

        return ms

    @deprecated(version="2.9.0", reason="Not needed with automatic translators")
    def missing_keys(self):
        """Nothing."""
        pass

    def available_locales(self) -> List[str]:
        """Return the available locales in the l10n folder.

        Returns:
            the list of str codes
        """
        return [f.name for f in Path(self._folder).glob("[!^._]*") if f.is_dir()]

    @versionadded(version="2.7.0")
    @classmethod
    def merge_dict(cls, folder: Path) -> dict:
        """Gather all the .json file in the provided l10n folder as 1 single json dict.

        The json dict will be sanitysed and the key will be used as if they were coming from 1 single file.
        be careful with duplication. empty string keys will be removed.

        Args:
            folder: the folder where all the .json files are stored

        Returns:
            the json dict with all the keys

        """
        final_json = {}
        for f in folder.glob("*.json"):
            tmp_dict = cls.delete_empty(json.loads(f.read_text()))
            final_json = {**final_json, **cls.sanitize(tmp_dict)}

        return final_json

    @versionadded(version="2.8.1")
    @classmethod
    def delete_empty(cls, d: dict) -> dict:
        """Remove empty strings ("") recursively from the dictionaries.

        This is to prevent untranslated strings from Crowdin to be uploaded. The dictionary must only embed dictionaries and no lists.

        Args:
            d: the dictionary to sanitize

        Returns:
            the sanitized dictionary

        """
        for k, v in list(d.items()):
            if isinstance(v, dict):
                cls.delete_empty(v)
            elif v == "":
                d.pop(k)

        return d

    @versionadded(version="2.10.0")
    def key_use(self, folder: Path, name: str) -> List[str]:
        """Parse all the files in the folder and check if keys are all used at least once.

        Return the unused key names.

        .. warning::

            Don't forget that there are many ways of calling Translator variables
            (getattr, save.cm.xxx in another variable etc...) SO don't forget to check
            manually the variables suggested by this method before deleting them

        Args:
            folder: The application folder using this translator data
            name: the name use by the translator in this app (usually "cm")

        Returns:
            the list of unused keys
        """
        # cannot set FORBIDDEN_KEY in the Box as it would lock another key
        FORBIDDEN_KEYS = ["_folder", "_default", "_target", "_targeted", "_match"]

        # sanitize folder
        folder = Path(folder)

        # get all the python files recursively
        py_files = []
        all_files = [f for f in folder.glob("**/*") if f.suffix in [".py", ".ipynb"]]
        for f in all_files:
            generated_files = [".ipynb_checkpoints", "__pycache__"]
            if all([err not in str(f) for err in generated_files]):
                py_files.append(f)

        # get the flat version of all keys
        keys = list(set(pd.json_normalize(self).columns) ^ set(FORBIDDEN_KEYS))

        # init the unused keys list
        unused_keys = []

        for k in keys:

            # by default we consider that the is never used
            is_present = False

            # read each python file and search for the pattern of the key
            # if it's find change status of the counter and exit the search
            for f in py_files:
                tmp = f.read_text()
                if f"{name}.{k}" in tmp:
                    is_present = True
                    break

            # if nothing is find, the value is still False and the key can be
            # added to the list
            is_present or unused_keys.append(k)

        return unused_keys
