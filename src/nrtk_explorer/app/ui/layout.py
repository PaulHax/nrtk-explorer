from pathlib import Path
from trame.ui.quasar import QLayout
from trame.widgets import quasar
from trame.widgets import html
from nrtk_explorer.app import ui

HORIZONTAL_SPLIT_DEFAULT_VALUE = 17
VERTICAL_SPLIT_DEFAULT_VALUE = 40


def parse_dataset_dirs(datasets):
    return [{"label": Path(ds).name, "value": ds} for ds in datasets]


class NrtkDrawer(html.Div):
    def __init__(
        self, dataset_paths=[], embeddings_app=None, filtering_app=None, transforms_app=None
    ):
        super().__init__(classes="q-pa-md q-gutter-md")

        with self:
            # DataSet card
            with ui.CollapsibleCard() as card:
                with card.slot_title:
                    html.Span("Dataset", classes="text-h6")
                with card.slot_content:
                    quasar.QSelect(
                        label="Dataset",
                        v_model=("current_dataset",),
                        options=(parse_dataset_dirs(dataset_paths),),
                        filled=True,
                        emit_value=True,
                        map_options=True,
                        dense=True,
                    )
                    quasar.QSlider(
                        v_model=("num_images", 15),
                        min=(0,),
                        max=("num_images_max", 25),
                        disable=("num_images_disabled", True),
                        step=(1,),
                    )
                    html.P(
                        "{{num_images}}/{{num_images_max}} images",
                        classes="text-caption text-center",
                    )
                    quasar.QToggle(
                        v_model=("random_sampling", False),
                        dense=False,
                        label="Random sampling",
                    )

            # Embeddings
            with ui.CollapsibleCard() as card:
                with card.slot_title:
                    html.Span("Embeddings", classes="text-h6")
                with card.slot_content:
                    embeddings_app.settings_widget()
                with card.slot_actions:
                    embeddings_app.compute_ui()

            # Annotations
            with ui.CollapsibleCard() as card:
                with card.slot_title:
                    quasar.QToggle(v_model=("annotations_enabled_switch", False))
                    html.Span("Model Inference", classes="text-h6")
                with card.slot_content:
                    quasar.QSelect(
                        label="Inference Model",
                        v_model=("inference_model", "facebook/detr-resnet-50"),
                        options=("inference_models", []),
                        filled=True,
                        emit_value=True,
                        map_options=True,
                    )

            # Transforms
            with ui.CollapsibleCard() as card:
                with card.slot_title:
                    quasar.QToggle(v_model=("transform_enabled_switch", False))
                    html.Span("Transform", classes="text-h6")
                with card.slot_content:
                    transforms_app.settings_widget()
                with card.slot_actions:
                    transforms_app.apply_ui()

            # Filters
            with ui.CollapsibleCard() as card:
                with card.slot_title:
                    html.Span("Category Filter", classes="text-h6")
                with card.slot_content:
                    filtering_app.filter_operator_ui()
                    filtering_app.filter_options_ui()
                with card.slot_actions:
                    filtering_app.filter_apply_ui()


class Splitter(quasar.QSplitter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self:
            self.slot_before = html.Template(raw_attrs=["v-slot:before"])
            self.slot_after = html.Template(raw_attrs=["v-slot:after"])


class NrtkToolbar(quasar.QHeader):
    def __init__(self, reload=None):
        super().__init__()
        with self:
            with quasar.QToolbar(classes="shadow-4"):
                quasar.QToolbarTitle("NRTK Explorer")
                if reload:
                    quasar.QBtn(
                        "Reload",
                        click=(reload,),
                        flat=True,
                    )
                quasar.QSpinnerBox(
                    v_show="trame__busy",
                    size="2rem",
                )


class NrtkExplorerLayout(QLayout):
    def __init__(
        self,
        server,
        reload=None,
        dataset_paths=None,
        embeddings_app=None,
        filtering_app=None,
        transforms_app=None,
        **kwargs,
    ):
        super().__init__(server, view="lhh LpR lff", classes="shadow-2 rounded-borders bg-grey-2")

        # Make local variables on state
        self.state.client_only("horizontal_split", "vertical_split")
        self.state.trame__title = "NRTK Explorer"

        with self:
            NrtkToolbar(reload=reload)
            with quasar.QPageContainer():
                with quasar.QPage():
                    with Splitter(
                        model_value=("horizontal_split", HORIZONTAL_SPLIT_DEFAULT_VALUE),
                        classes="inherit-height",
                        before_class="inherit-height zero-height scroll",
                        after_class="inherit-height zero-height",
                    ) as split_drawer_main:
                        with split_drawer_main.slot_before:
                            NrtkDrawer(
                                dataset_paths=dataset_paths,
                                embeddings_app=embeddings_app,
                                filtering_app=filtering_app,
                                transforms_app=transforms_app,
                            )
                        with split_drawer_main.slot_after:
                            with Splitter(
                                v_model=("vertical_split", VERTICAL_SPLIT_DEFAULT_VALUE),
                                limits=("[0,100]",),
                                horizontal=True,
                                classes="inherit-height zero-height",
                            ) as split_scatter_table:
                                with split_scatter_table.slot_before:
                                    embeddings_app.visualization_widget()

                                with split_scatter_table.slot_after:
                                    transforms_app.dataset_widget()
