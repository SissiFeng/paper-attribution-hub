"""Versioned package descriptors and deterministic dependency resolution."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PackageKind = Literal["scientific_core", "domain", "capability", "evidence"]
DependencyKind = Literal[
    "scientific_core",
    "parent_domain",
    "capability",
    "evidence",
]


class PackageGraphError(ValueError):
    pass


class PackageGraphModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PackageReference(PackageGraphModel):
    package_id: str = Field(min_length=1)
    package_version: str = Field(min_length=1)

    @property
    def coordinate(self) -> str:
        return f"{self.package_id}@{self.package_version}"


class PackageDependency(PackageReference):
    dependency_kind: DependencyKind
    required_layers: list[str] = Field(default_factory=list)
    required_content_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class PackageDescriptor(PackageReference):
    schema_version: str = "domain-package-descriptor-v0.1"
    package_kind: PackageKind
    domain: str = Field(min_length=1)
    facets: list[str] = Field(default_factory=list)
    dependencies: list[PackageDependency] = Field(default_factory=list)


class EvidencePackageDescriptor(PackageDescriptor):
    package_kind: Literal["evidence"] = "evidence"
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PackageGraphReport(PackageGraphModel):
    schema_version: str = "domain-package-graph-report-v0.1"
    root: PackageReference
    valid: bool
    resolution_order: list[str]
    dependency_closure: list[str]
    edges: dict[str, list[str]]


def _validate_dependency_kind(
    source: PackageDescriptor,
    dependency: PackageDependency,
    target: PackageDescriptor,
) -> None:
    expected_kind: dict[DependencyKind, PackageKind] = {
        "scientific_core": "scientific_core",
        "parent_domain": "domain",
        "capability": "capability",
        "evidence": "evidence",
    }
    if target.package_kind != expected_kind[dependency.dependency_kind]:
        raise PackageGraphError(
            f"Dependency kind mismatch for {source.coordinate}: "
            f"{dependency.coordinate} is {target.package_kind}, expected "
            f"{expected_kind[dependency.dependency_kind]}"
        )
    if dependency.dependency_kind == "evidence":
        if dependency.required_content_sha256 is None:
            raise PackageGraphError(
                "Evidence dependencies require a content SHA-256 digest"
            )
        if (
            not isinstance(target, EvidencePackageDescriptor)
            or target.content_sha256 != dependency.required_content_sha256
        ):
            raise PackageGraphError(
                f"Evidence content digest mismatch for {target.coordinate}"
            )


def resolve_package_graph(
    descriptors: list[PackageDescriptor],
    *,
    root: PackageReference,
) -> PackageGraphReport:
    """Resolve one package closure, rejecting missing nodes and cycles."""
    by_coordinate: dict[str, PackageDescriptor] = {}
    for descriptor in descriptors:
        if descriptor.coordinate in by_coordinate:
            raise PackageGraphError(
                f"Duplicate package coordinate: {descriptor.coordinate}"
            )
        by_coordinate[descriptor.coordinate] = descriptor
    if root.coordinate not in by_coordinate:
        raise PackageGraphError(f"Root package is missing: {root.coordinate}")

    states: dict[str, Literal["visiting", "visited"]] = {}
    stack: list[str] = []
    resolution_order: list[str] = []
    edges: dict[str, list[str]] = {}

    def visit(coordinate: str) -> None:
        state = states.get(coordinate)
        if state == "visited":
            return
        if state == "visiting":
            cycle_start = stack.index(coordinate)
            cycle = " -> ".join([*stack[cycle_start:], coordinate])
            raise PackageGraphError(f"Package dependency cycle: {cycle}")
        states[coordinate] = "visiting"
        stack.append(coordinate)
        descriptor = by_coordinate[coordinate]
        dependency_coordinates: list[str] = []
        for dependency in sorted(
            descriptor.dependencies, key=lambda item: item.coordinate
        ):
            target = by_coordinate.get(dependency.coordinate)
            if target is None:
                raise PackageGraphError(
                    "Missing package dependency: "
                    f"{descriptor.coordinate} requires {dependency.coordinate}"
                )
            _validate_dependency_kind(descriptor, dependency, target)
            dependency_coordinates.append(dependency.coordinate)
            visit(dependency.coordinate)
        edges[coordinate] = dependency_coordinates
        stack.pop()
        states[coordinate] = "visited"
        resolution_order.append(coordinate)

    visit(root.coordinate)
    return PackageGraphReport(
        root=root,
        valid=True,
        resolution_order=resolution_order,
        dependency_closure=[
            coordinate
            for coordinate in resolution_order
            if coordinate != root.coordinate
        ],
        edges={key: edges[key] for key in sorted(edges)},
    )
