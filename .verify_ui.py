import app as jeevanroute

demo = jeevanroute.build_ui()
demo.queue().launch(
    server_name="127.0.0.1",
    server_port=7861,
    css=jeevanroute.UI_CSS,
    theme=jeevanroute.gr.themes.Soft(),
)
