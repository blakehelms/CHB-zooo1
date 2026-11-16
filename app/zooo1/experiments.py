"""Future task integration hook. No task, classifier, or analysis is implemented."""
class ExperimentHook:
    def on_start(self, emit):
        self.emit = emit
    def on_samples(self, samples):
        pass
    def on_marker(self, name):
        pass
    def on_stop(self, outcome):
        pass
