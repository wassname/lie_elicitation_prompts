import os
from elk.promptsource.templates import DatasetTemplates, TEMPLATES_FOLDER_PATH

class LocalDatasetTemplates(DatasetTemplates):

    @property
    def folder_path(self) -> str:
        # if we provide a path to a directory, use it
        if os.path.isdir(self.dataset_name):
            return self.dataset_name
        elif self.subset_name:
            return os.path.join(
                TEMPLATES_FOLDER_PATH, self.dataset_name, self.subset_name
            )
        else:
            return os.path.join(TEMPLATES_FOLDER_PATH, self.dataset_name)

